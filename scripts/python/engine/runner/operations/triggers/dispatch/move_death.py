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


def pre_move_triggers(state: State, mover_id: int, dest_tile=None) -> list[dict]:
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

    `dest_tile` = la DESTINATION `(col, row)` du pas -- le ctor nomme recoit la liste `position` a la
    fois en `casterTiles` (7e arg) et en `targetTiles` (10e), donc les DEUX portent la tuile
    d'ARRIVEE. Un `CreateTrigger` qui compare `Tiles(Actor)` (la tuile de DEPART, l'unite n'ayant pas
    encore bouge) a ce slot teste « est-ce un VRAI deplacement ? ». Seul `MoveUnitOperation.execute`
    le renseigne ; None = non threade, et le consommateur doit le DIRE.

    Consommateurs portes :
      * `GhostReviveAbility`/`TimeFluxReviveAbility` (#213) : Toth qui bouge laisse un time-ghost sur
        sa tuile de DEBUT DE TOUR ;
      * 1er des cinq retraits de `GhostEffect` : un ghost dont le poseur rebouge disparait ;
      * `HatefulAssaultAbility` (1038, `blackTerminator`) : attaque d'opportunite sur l'ennemi
        adjacent qui s'ecarte -- SEUL consommateur de `dest_tile` a ce jour.
    No-op si aucun trigger ne matche."""
    ev = TriggerEvent(EventTriggerType.PreUnitMove, mover_id, mover_id, ranged=False, profile=None,
                      dest_tile=dest_tile)
    return evaluate_trigger_operation(state, ev)


def unit_position_changed_1_triggers(state: State, unit_id: int,
                                     movement_steps: int | None = None) -> list[dict]:
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

    `movement_steps` = le 5e argument d'`EvaluateAfterMoveTriggers`, seul emetteur du build a le
    renseigner ; les DEUX autres emetteurs de cet event le laissent NUL, et c'est LU :
    `IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects` (push) et
    `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` passent 0 au 30e parametre du
    ctor d'`AbilityEntities`. `None` par defaut = ce `Nullable` vide.
    Consommateur : `FullThrottleAbility` (cf. `triggers/loki/full_throttle.py`).
    No-op si aucun trigger ne matche."""
    ev = TriggerEvent(EventTriggerType.UnitPositionChanged_1, unit_id, unit_id,
                      ranged=False, profile=None, movement_steps=movement_steps)
    return evaluate_trigger_operation(state, ev)


def unit_position_changed_2_triggers(state: State, unit_id: int,
                                     movement_steps: int | None = None) -> list[dict]:
    """Vecteur `On(UnitPositionChanged_2 = 0x1d = 29)` — TROISIEME et dernier event
    d'`EvaluateAfterMoveTriggers`, emis aussi par `ReviveUnitOperation$$SetRevivePosition`.
    Consommateur porte : `DecoysAndMisdirection_BuffFriends` (G2). Foyer partage avec
    `after_move_triggers` (qui l'emettait deja inline).

    `movement_steps` : le natif construit UN SEUL `AbilityEntities` pour les TROIS events
    d'`EvaluateAfterMoveTriggers` -- ce champ est donc porte par `On(0x1d)` et `On(4)` autant que
    par `On(0x24)`. Aucun consommateur porte ne le lit sur ces deux-la, mais le threader est le
    mirror ; ne pas le faire creerait un ecart invisible le jour ou l'un d'eux entre au registre."""
    ev = TriggerEvent(EventTriggerType.UnitPositionChanged_2, unit_id, unit_id,
                      ranged=False, profile=None, movement_steps=movement_steps)
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


def after_move_triggers(state: State, mover_id: int,
                        movement_steps: int | None = None, *,
                        is_interim_step: bool = False,
                        arrive_at_final_tile: bool = True) -> list[dict]:
    """Vecteur after-move (mirror `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers → dispatch).
    Le natif émet, dans l'ordre, `On(0x24=UnitPositionChanged_1)`, `On(4=UnitAfterMove)` (overwatch) PUIS
    `On(0x1d=UnitPositionChanged_2)`. On dispatche les trois : `On(0x24)` déclenche la POSE de couverture
    de la tuile d'arrivée (`LightCoverAbility`, tile-ability écoutant cet event — résidu O3, cf.
    `triggers/tiles.py::light_cover_on_enter`) ; `On(0x1d)` déclenche DecoysAndMisdirection (G2 —
    ennemi/allié qui marche sur un decoy allié crushé par `_kill_steppable_units`, G1). No-op si aucun
    trigger ne matche (ou pas de board/rng).

    ORDRE NATIF COMPLET, lu au décompilé d'`IdunBattle.Operations.MoveUnitOperation$$Execute` (les deux
    events ENCADRANTS sont désormais portés, cf. les vecteurs dédiés ci-dessous) :
        AddMoveEvent(s) -> **KillSteppableUnits** (chaque crushé joue `KillUnitOperation$$Execute`
                           EN ENTIER, `On(0x35 = PostUnitKill)` compris)
        -> UpdateCharging -> SetMovedFlag -> **Add(UnitFlag.ArrivedAtFinalTile=1)**
        -> EvaluateAfterMoveTriggers (`On(0x24)` / `On(4)` / `On(0x1d)`)
        -> si le flag 1 venait d'être AJOUTÉ : **`On(0x1c=ArrivedAtFinalTile)`**.
    `arrived_at_final_tile_triggers` est donc émis EN QUEUE (l'event 0x1c suit les after-move).
    ⚠ Les cinq events de mort du crush, `On(0x35)` COMPRIS, partent depuis `MoveUnitOperation` AVANT
    d'entrer ici (`movement.py::_kill_steppable_units`) : ce vecteur n'en publie AUCUN
    (#462-r4b-r1-r1-r1-r1-c-r3-r1-r4 — il publiait `On(0x35)` en tête, donc APRÈS
    `UpdateCharging`/`SetMovedFlag`, et pour le seul chemin MOVE).

    `movement_steps` = le 5e argument natif d'`EvaluateAfterMoveTriggers`, propage aux TROIS events
    (un seul `AbilityEntities` cote natif). Il vient de `MoveUnitOperation.last_movement_steps` ;
    un appelant qui ne modelise pas de chemin le laisse `None` = le `Nullable` VIDE, ce qui rend 0 a
    `MovementSteps()` -- FIDELE, puisque le natif n'a lui non plus rien a y mettre hors d'un
    `MoveUnitOperation$$Execute`.

    `is_interim_step` = le **6e argument natif** d'`EvaluateAfterMoveTriggers` (nom LU dans la
    signature IL2CPP, pas devine), qui vaut l'octet `MoveUnitOptions+0x14` aux DEUX call-sites de
    `MoveUnitOperation$$Execute`. Le corps natif est, lu au decompile (#448-r1-r1-r2-r1) :

        publish On(0x24 = UnitPositionChanged_1)
        if (isInterimStep) return;                 <- LA COUPURE
        publish On(4  = UnitAfterMove)             <- overwatch
        publish On(0x1d = UnitPositionChanged_2)

    ⇒ un pas INTERMEDIAIRE ne declenche NI l'overwatch NI `On(0x1d)`. C'est la face INVERSE du
    vecteur, et elle est PORTEE ici (brancher indistinctement serait l'erreur symetrique, du cote
    permissif). Corroboration independante : la case-doc de `TheBetrayer` avait deja identifie
    « behaviour `+0x80` = flag SUPPRESS de `On(4)`, defaut 0 = overwatch ACTIF » -- et
    `MoveUnitBehaviour+0x80` est exactement le selecteur que `MoveUnitBehaviour$$Execute` empaquette
    dans `MoveUnitOptions+0x14`.

    `arrive_at_final_tile` = mirror de l'octet `MoveUnitOptions+0x10`, gate NEGATIF du natif
    (`if (options+0x10 == 0) { newlyAdded = UnitFlagsComponent.Add(1) }`, puis `On(0x1c)` publie SSI
    `newlyAdded`). Il est **INVERSE** par `MoveUnitBehaviour$$Execute` (`CONCAT11(...) ^ 0x101`) a
    partir du selecteur `MoveUnitBehaviourOptions+0x18` dont le defaut est FAUX ⇒ pour une feuille
    DSL a options nulles l'octet vaut **1** ⇒ ni le flag `ArrivedAtFinalTile`, ni `On(0x1c)`. Le
    mouvement JOUEUR, lui, passe des options entierement nulles ⇒ octet 0 ⇒ flag pose et `On(0x1c)`
    emis (comportement historique, live-valide, INCHANGE)."""
    out: list[dict] = []
    # `On(0x24 = UnitPositionChanged_1)` — PREMIER des trois events d'`EvaluateAfterMoveTriggers`.
    # Consommateur porté : `LightCoverAbility` (tile-ability : la tuile de cover pose l'effet 1013 sur
    # l'unité qui vient d'y arriver). Les tile-abilities ne sont pas dans le registre d'effet-triggers
    # (elles sont portées par le tile-def, pas par un effet) → appel direct, comme `dry_bush_fire_spread`
    # / `first_aid_heal`. No-op hors tuile de cover.
    from ..tiles import light_cover_on_enter
    out += light_cover_on_enter(state, mover_id)
    # ... et le dispatch GENERIQUE du meme `On(0x24)` pour les effet-triggers qui l'ecoutent (#213 :
    # retrait n°3 de `GhostEffect` -- une autre unite arrive sur la tuile du ghost).
    out += unit_position_changed_1_triggers(state, mover_id, movement_steps=movement_steps)
    if is_interim_step:
        return out                     # `if (isInterimStep) return;` -- NI `On(4)` NI `On(0x1d)`
    ev = TriggerEvent(EventTriggerType.UnitAfterMove, mover_id, mover_id, ranged=False, profile=None,
                      movement_steps=movement_steps)
    out += evaluate_trigger_operation(state, ev)
    # G2 : `On(0x1d=UnitPositionChanged_2)` émis APRÈS `On(4)` par le même `EvaluateAfterMoveTriggers` natif.
    out += unit_position_changed_2_triggers(state, mover_id, movement_steps=movement_steps)
    if not arrive_at_final_tile:
        return out                     # `options+0x10 != 0` : ni le flag, ni `On(0x1c)`
    return out + arrived_at_final_tile_triggers(state, mover_id)


def post_unit_kill_triggers(state: State, killed_id: int,
                            killer_id: Optional[int] = None) -> list[dict]:
    """Vecteur `On(PostUnitKill = 0x35 = 53)` — **5e et DERNIER** des events de mort émis par
    `IdunBattle.Operations.KillUnitOperation$$Execute` (séquence lue au décompilé et déjà documentée
    par `pre_unit_death_2_triggers` : `On(1)` -> `On(2)` -> `On(0)` -> `On(0x36 = UnitDefeated)` -> `On(0x35 = PostUnitKill)`).
    `actor` = le TUEUR, `target`/`dying` = la victime. Même `AbilityEntities` que les quatre autres
    (bâti UNE fois, publié tel quel — cf. `after_death_triggers`), d'où l'ordre d'arguments et le
    repli `actor = dying` quand le tueur est absent, identiques aux quatre.

    APPELÉ DEPUIS LE FOYER `damage.py::_kill_unit_operation`, à sa place native — pas depuis le
    pipeline de move (#462-r4b-r1-r1-r1-r1-c-r3-r1-r4). Son RANG exact, lu à la PILE D'ACCOLADES du
    décompilé `rnca9r7q6c` et non à la profondeur (les deux valent 9, et c'est ce qui avait fait
    écrire « TOUS à l'intérieur du bloc, sans else ») :

        L1111  if (unitComponent != null) {
        L1131      if (!PendingRevive.HasValue) {          <- GARDE REVIVE
                       ... On(2) / RemoveEffects(0,1) / On(0) / On(0x36) ...
        L1971          if (health.hp > 0) return;          <- GARDE HEAL
                       RemoveEffects(2) ; processor.<slot 0x55>
        L1997      } else { matchState.<slot 0x63>(killed) }   <- le revive s'applique
                   PendingRevive@+0xa8..+0xe8 = 0
        L2033      if (dispatcher != null) { On(0x35) ; return }

    ⇒ `On(0x35)` est le SEUL des cinq qui ne soit PAS sous la garde revive : il part **dans les deux
    branches**, y compris quand un revive ANNULE la mort. Il est en revanche sauté par le `return`
    de la garde HEAL. Aucune gate sur `KillUnitOptions` ne le conditionne (les quatre octets lus le
    sont ailleurs) ⇒ il part pour TOUTES les voies de mort qui traversent `Execute` : dégât, crush
    (`*$$KillSteppableUnits` de move / revive / resurrect / spiritual_leader) et `KillUnitBehaviour`.

    Consommateur porté : `CosmicHorrorOnMoveAbility` (`On(0x35 = PostUnitKill) & OwnerIsActor & AreFriends &
    HasTrait(target, Decoy)` — aucune gate de MOUVEMENT malgré son nom, lu au décompilé de
    `...CosmicHorror_OnMoveAbility$$CreateTrigger`) : le Patermine se soigne dès qu'il est le TUEUR
    d'un allié `Decoy`, quelle que soit la voie de mort. No-op si rien ne matche."""
    ev = TriggerEvent(EventTriggerType.PostUnitKill,
                      killer_id if killer_id is not None else killed_id, killed_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=killed_id)
    return evaluate_trigger_operation(state, ev)


# `post_unit_kill_triggers_for_move` A ÉTÉ SUPPRIMÉE (#462-r4b-r1-r1-r1-r1-c-r3-r1-r4).
#
# Elle ré-identifiait les crushés par CO-LOCALISATION (mort + `Steppable` + sur la tuile du mover)
# parce que le port crushait alors SANS émettre aucun des cinq events de mort, et publiait
# `On(0x35)` APRÈS coup, depuis `after_move_triggers`. Depuis `-c-r3-r1-r1` le crush passe par
# `KillUnitOperation$$Execute` (`movement.py::_kill_steppable_kill_unit`), et depuis CETTE tranche
# ce foyer publie lui-même `On(0x35)` à son rang natif : la ré-identification n'a plus d'objet, et
# la garder produirait une DOUBLE émission pour le seul chemin MOVE.
#
# La garantie qu'elle portait — « un `On(PostUnitKill)` émis pour un cadavre-au-chargement est un
# kill QUI N'A PAS EU LIEU » — est désormais tenue PAR CONSTRUCTION, un cran plus haut et plus
# étroitement : `_kill_steppable_units` ne crushe que ce qui est `uc.alive`, donc un cadavre
# co-localisé n'entre jamais dans `_kill_unit_operation`. Elle reste ASSERTÉE, sur le chemin réel,
# par `test_ctx_traits_substrat_ventilation_offline.py`.


def pre_unit_fled_triggers(state: State, unit_id: int, triggering_ability=None) -> list[dict]:
    """Vecteur `On(PreUnitFled = 0x33 = 51)` — le TOUT PREMIER geste d'
    `IdunBattle.Operations.FleeOperation$$Execute`, LU au decompile (build `rnca9r7q6c`) :

        IOperationProcessor.<slot 81 = EvaluateAbilities>( actor = unit, caster = unit,
                                                           target = unit,
                                                           eventType = 0x33 = PreUnitFled,
                                                           abilityOrEffect = triggeringAbilityOrEffect )
        if (UnitExtensions.IsDead(unit)) return;        // <- LA FUITE EST ABANDONNEE

    Le slot **81** est celui d'`EvaluateAbilities` (`data/symbols/<build>/metadata/
    ioperationprocessor_slots.tsv`, champ `slot` du metadata, arite 5). L'`AbilityEntities` natif
    recoit TROIS FOIS la meme unite -> **actor = caster = target = la fuyarde**.

    C'est ce couple emission/`IsDead` qui porte le « it is executed **instead** » de
    `SummaryExecution` (#955) : le passif TUE l'unite dans son behaviour, `IsDead` devient vrai, et
    le natif sort AVANT `RecordFlee`, `RemoveUnit`, `UnitFlag 9`, `On(0x34 = UnitFled)` et
    `On(0x36 = UnitDefeated)`. Aucun de ces cinq etages n'a lieu.

    `triggering_ability` = l'`AbilityOrEffect` declenchant, que le natif propage depuis le
    `DSLBehaviors$$Flee` de `BattleFatigueAbility$$CreateBehaviour` -- c'est LUI que
    `SummaryExecutionAbility$$CreateTrigger` compare (`TriggeringAbilityIs(0x401 = BattleFatigue)`).
    Le port le fait passer par le champ `TriggerEvent.triggering_ability` : contrairement au vecteur
    MORT (ou le champ natif `CurrentAbility` n'est pas renseigne), CE vecteur-ci le porte, parce que
    l'appelant est l'ability elle-meme. `None` = canal non seede -> le gate `TriggeringAbilityIs`
    d'un consommateur ne peut pas trancher.

    No-op si aucun trigger ne matche."""
    ev = TriggerEvent(EventTriggerType.PreUnitFled, unit_id, unit_id,
                      ranged=False, profile=None, triggering_ability=triggering_ability)
    return evaluate_trigger_operation(state, ev)


def unit_fled_triggers(state: State, fled_id: int, triggering_unit_id: Optional[int] = None,
                       triggering_ability=None) -> list[dict]:
    """Vecteur `On(UnitFled = 0x34 = 52)` — AVANT-DERNIER event d'
    `IdunBattle.Operations.FleeOperation$$Execute`, LU au decompile (build `rnca9r7q6c`) :

        UnitFlagsComponent.Add(unit, 9 = UnitFlag.Fled)
        FleeOperation.RemoveEffects(unit, step 1)
        IOperationProcessor.<slot 81 = EvaluateAbilities>( actor = triggeringUnit,
                                                           caster = triggeringUnit,
                                                           target = unit,
                                                           eventType = 0x34 = UnitFled,
                                                           abilityOrEffect = triggeringAbilityOrEffect )
        IOperationProcessor.<slot 81>( ... , eventType = 0x36 = UnitDefeated, ... )   # meme AbilityEntities

    ⚠ **L'ASYMETRIE AVEC `On(PreUnitFled)` EST LUE, PAS SUPPOSEE.** Le premier geste de l'Operation
    passe la fuyarde TROIS FOIS (`(plVar1, unit, unit, unit, 0x33, ...)` -> actor = caster = target),
    tandis que CES DEUX events-ci passent `(plVar1, triggeringUnit, triggeringUnit, unit, 0x34/0x36,
    ...)` : l'ACTEUR est **celui qui a CAUSE la fuite**, la CIBLE est la fuyarde. C'est exactement ce
    qui rend `HeadClaimerAbility` (`get_OwnerIsActor`) capable de compter une tete sur une fuite --
    inverser les deux slots rendrait la branche inerte d'une AUTRE facon, sans erreur.

    `triggering_unit_id` = le `triggeringUnit` du call-site. Son SEUL appelant porte le derive du
    selecteur `Caster@<DSLSelectors+0x48>`, que `BattleFatigueAbility$$CreateBehaviour` passe en 2e
    argument de `IdunBattleLogic.Entities.DSLBehaviors$$Flee` ::

        DSLBehaviors.Flee( unit          = Owner@<DSLSelectors+0x30>,     // la fuyarde
                           triggeringUnit= Caster@<DSLSelectors+0x48>,    // <- ce canal
                           position      = CasterTiles@<DSLSelectors+0x58>,
                           defendingUnit = Target@<DSLSelectors+0x60>,    // l'allie qui vient de mourir
                           triggeringAbility = AbilityOrEffect(BattleFatigue),
                           damageProfile = KillingDamageProfile(Target@+0x60) )

    -- et `FleeBehaviour$$.ctor` range bien ces arguments en `+0x58/+0x60/+0x68/+0x70/+0x78/+0x98`,
    que `FleeBehaviour$$Execute` re-passe dans CET ordre au slot `0x48 = Flee`.

    `None` = canal non seede -> le vecteur est emis avec `actor = target = la fuyarde`, ce qui FERME
    `get_OwnerIsActor` pour tout tiers. Degradation RESTRICTIVE assumee : sans caster identifie, on
    ne CREDITE personne d'une tete qu'on ne peut pas attribuer.

    No-op si aucun trigger ne matche."""
    actor = int(triggering_unit_id) if triggering_unit_id is not None else int(fled_id)
    ev = TriggerEvent(EventTriggerType.UnitFled, actor, int(fled_id),
                      ranged=False, profile=None, triggering_ability=triggering_ability)
    return evaluate_trigger_operation(state, ev)


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
    POST-push). No-op si aucun trigger ne matche. Appelé par
    `DisplaceUnitOperation.execute` (displace.py) après un push réussi.

    `On(0x1d)` — TROISIÈME et dernier des events du natif, dispatché depuis #462-r4b-r1-r1-r1-r1-b.
    Il était jusque-là omis (« concern séparé, non validé »), et cette omission était MESURABLE :
    le trigger (b) d'`ABondEffect` (`BondRemoveOnRangeExceeded`) n'écoute QUE cet event, donc un
    taunt POUSSÉ hors de portée survivait offline alors que le natif le retire (mesuré : natif
    `[25,26,27,1237] -> []`, port inchangé). Le vecteur et le trigger sont livrés ensemble : l'un
    sans l'autre ne mord pas."""
    from ..tiles import light_cover_on_enter     # `On(0x24)` — tile-ability, hors registre d'effets
    out = light_cover_on_enter(state, pushed_id)
    # dispatch GENERIQUE du meme `On(0x24)` (retrait n°3 de `GhostEffect`, #213) : une unite POUSSEE
    # sur la tuile d'un ghost le fait disparaitre exactement comme si elle y avait marche.
    out += unit_position_changed_1_triggers(state, pushed_id)
    ev = TriggerEvent(EventTriggerType.UnitDisplaced, pusher_id, pushed_id, ranged=False, profile=None)
    out += evaluate_trigger_operation(state, ev)
    # `On(0x1d = UnitPositionChanged_2)` — le natif le publie APRÈS `On(0x23)`, avec le MÊME
    # `AbilityEntities` {actor = caster = pusher, target = pushed} (lu :
    # `DisplaceUnitOperation$$EventAndAbilitiesAndEffects` passe `caster, caster, target` aux TROIS
    # appels, seul l'`eventId` change — 0x24, puis 0x23, puis 0x1d).
    # ⚠ `unit_position_changed_2_triggers` construit {actor = target = l'unité}, ce qui est le
    # contrat de l'émetteur `MoveUnitOperation` ; ici l'ACTEUR natif est le POUSSEUR. Aucun
    # consommateur porté de `On(0x1d)` ne lit l'acteur (`BondRemoveOnRangeExceeded` lit le porteur de
    # l'effet et son bondé, `DecoysAndMisdirection_BuffFriends` lit `AreEnemies(owner, actor)`), mais
    # on pose l'événement à la MAIN plutôt que de réutiliser le helper : la paire actor/target est
    # une donnée du natif, pas un détail de plomberie.
    out += evaluate_trigger_operation(
        state, TriggerEvent(EventTriggerType.UnitPositionChanged_2, pusher_id, pushed_id,
                            ranged=False, profile=None))
    return out


def after_death_triggers(state: State, dying_id: int, killer_id: Optional[int],
                         overkill: bool = False) -> list[dict]:
    """Vecteur MORT (mirror `IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent → dispatch). Construit l'événement `On(1)`
    {killer=0x158, dying=0x178, overkill} et lance `evaluate_trigger_operation`. Déclenche les accumulations
    ActOfFaith (allié Imperial qui meurt ou tue) + FinalJustice (l'unité mourante riposte, sauf overkill).
    `actor_id`/`target_id` reflètent killer/dying pour le dispatch générique. No-op si aucun trigger ne
    matche.

    CANAUX D'ABILITY SUR CE VECTEUR (#301) — vaut pour les CINQ events de
    `IdunBattle.Operations.KillUnitOperation$$Execute` (`On(1)`, `On(2)`, `On(0)`, `On(54 = UnitDefeated)`, `On(53 = PostUnitKill)`),
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
    `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` (`RunPhase(PhaseType.ProcessDeaths /*0xc*/)` -> `KillUnit` ->
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

    Consommateurs portes : la famille DEATH-NOVA (`IdunBattleLogic.Entities.DSLTriggers$$OnPreDeath2` ->
    `IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent(2, a, b)) — `ExplodesAbility` (trait Explodes) et `PutridExplosion_Ability`
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
    `On(1)` (`after_death_triggers`) et `On(0x36 = UnitDefeated)` (`unit_defeated_triggers`) mais PAS `On(0)` — d'ou ce
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
    HAUT** (`FUN_1800280e0(0x50, ..., 0x3d)` = `On(PreEffectAdded)` juste apres la construction de l'`AbilityEntities`, AVANT le
    gate cible-nulle, AVANT le gate << deja present >> et AVANT le gate d'immunite `HasFlag(target,6)`).
    => l'evenement fire meme quand l'effet n'est finalement PAS applique (semantique << would have >>).

    `AbilityEntities.ctor(source, source, target)` -> **actor = la SOURCE** de l'effet ; `target` = la
    cible ; `triggering_effect` = le type pose (lu par `TriggeringEffectIs`). Consommateur : branche 2 de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger`. No-op si rien ne matche.

    Les DEUX canaux d'ability sont poses par `_effect_vector_triggers` (#306) : la POSE ecrit `+0x60`
    ET `+0x98` avec le MEME `AbilityOrEffect(effectType)`."""
    return _effect_vector_triggers(state, int(EventTriggerType.PreEffectAdded),
                                   source_id, target_id, effect_type, removing=False)


def effect_added_triggers(state: State, source_id: Optional[int], target_id: Optional[int],
                          effect_type: int) -> list[dict]:
    """Vecteur `On(EffectAdded = 0x3e = 62)` -- DEUXIEME des trois events d'
    `IdunBattle.Operations.AddEffectOperation$$Execute`, publie **APRES** `$$RemoveExistingEffect` et
    `$$AddNewEffect`, donc APRES la materialisation reelle de l'entite-effet. C'est toute la
    difference avec son jumeau `On(0x3d = PreEffectAdded)`, emis TOUT EN HAUT (semantique
    << would have >>) : celui-ci ne fire QUE si la pose a abouti.

    Emplacement LU aux octets, pas deduit : le balayage de l'immediat `0x3e` dans le segment de code
    ne le trouve qu'a **UN** site d'`IdunBattle.Operations` -- `AddEffectOperation$$Execute+0xd0b`
    (`mov ecx, 0x50` / `mov r9d, 0x3e` / `call` du meme publieur que le `0x3d` de +0x50d), et la
    sequence d'appels qui precede est `RemoveExistingEffect` (+0xc25) -> `AddNewEffect` (+0xc4e) ->
    publication (+0xd37).

    MEME `AbilityEntities` que la pre-pose (le natif la batit UNE fois par `Execute` et la publie
    trois fois : `0x3d`, `0x3e`, `0x46`), donc MEMES canaux : `actor` = la SOURCE de l'effet, `target`
    = la cible, et les DEUX slots d'ability portent `AbilityOrEffect(effectType)` (#306) -- ce qui
    rend `CurrentAbilityIs(<effet>)` ET `TriggeringEffectIs(<effet>)` vrais, indiscernables.

    Consommateurs portes : la branche 1 d'
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EcstaticSlaughterAbility$$CreateTrigger`
    (`On(0x3e) & CurrentAbilityIs(AbilityOrEffect(EffectType.ThrillSeekers = 0x59a)) &
    get_OwnerIsTarget`) et `TerminatorArmourActivateOnEffectAdded`, qui etait enregistre sur cet
    event **sans qu'aucun emetteur n'existe** -- il reste structurellement inerte pour une autre
    raison (son seul poseur est un `OnOwnerSpecificAbilityInit` one-shot), et son `matches` est gate
    sur `triggering_effect == 1147`, donc l'emission ne l'arme pas. No-op si rien ne matche."""
    return _effect_vector_triggers(state, int(EventTriggerType.EffectAdded),
                                   source_id, target_id, effect_type, removing=False)


def pre_effect_removed_triggers(state: State, target_id: Optional[int],
                                effect_type: int) -> list[dict]:
    """Vecteur `On(PreEffectRemoved=0x3f=63)` — premier des trois events de
    `IdunBattle.Operations.RemoveEffectOperation$$Execute`, publie APRES les deux gates d'idempotence
    (`EffectComponent+0x5f` deja retire, `+0x5e` retrait en cours) et AVANT toute revocation.

    `actor`/`caster` (+0x00/+0x08) sont VIDES cote natif -- le memset n'est suivi d'aucune ecriture --
    donc le port ne threade PAS de source : seul le PORTEUR est connu (`target` = `owner` = +0x10/+0x18).
    C'est `CurrentAbilityIs` qui porte l'effet retire ; tout `TriggeringEffectIs` y est faux (#306).

    AUCUN consommateur porte n'ecoute encore `On(63 = PreEffectRemoved)` : l'emission est le MIRROR, et c'est elle qui
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

    MEME `AbilityEntities` que `On(63 = PreEffectRemoved)` : la struct est batie UNE fois puis publiee telle quelle
    (le port la reconstruit a l'identique via `_effect_vector_triggers`). Memes canaux, meme asymetrie.
    No-op si rien ne matche."""
    return _effect_vector_triggers(state, int(EventTriggerType.EffectRemoved),
                                   None, target_id, effect_type, removing=True)


def unit_became_targetable_triggers(state: State, target_id: Optional[int],
                                    effect_type: int) -> list[dict]:
    """Vecteur `On(UnitBecameTargetable = 0x3b = 59)` — TROISIEME et DERNIER event d'
    `IdunBattle.Operations.RemoveEffectOperation$$Execute`, publie APRES `On(0x40 = EffectRemoved)`
    et son `Inform(4)`, sous un gate de TYPE que le natif ecrit ainsi (queue du corps) :

        if (EffectsDatabase.GetEffect(effectComponent.Type@+0x58) is
            IdunBattle.Entities.Effects.Common.UntargetableEffect)  { On(0x3b) ; Inform(5) }

    ⚠ LE NOM DE LA CLASSE TESTEE EST LU, PAS DEDUIT. Le pseudo-C ne rend qu'un
    `DAT_<slot>` (un `Il2CppClass**` a zero sur disque). Le MEME slot est lu par TROIS fonctions --
    `AddEffectOperation$$Execute` (gate symetrique d'`On(0x46 = UnitBecameUntargetable)`),
    `RemoveEffectOperation$$Execute` (ici), et
    `IdunBattle.Core.Services.EffectsDatabase.<>c$$<InitializeEffects>b__14_576`, qui **alloue** ce
    type et appelle `IdunBattle.Entities.Effects.Common.UntargetableEffect$$.ctor`. C'est cette
    troisieme xref qui NOMME la classe.

    Cote port, le domaine de ce predicat existe deja et est le FOYER UNIQUE de la non-ciblabilite :
    `entities/effects/aura_selectors.py::UNTARGETABLE_EFFECT_TYPES` (les feuilles d'
    `ATeleportingEffect` REELLEMENT portees ET confrontees sur ce canal ; sa docstring dit pourquoi
    on n'y inscrit rien de speculatif). Le gate vit chez l'APPELANT
    (`operations/remove_effects.py::remove_effect_instance`), pas ici : ce module ne construit que
    des vecteurs.

    MEME `AbilityEntities` que les deux events precedents -- la struct est batie UNE fois en tete de
    l'Operation et publiee telle quelle. Donc, exactement comme eux : `actor`/`caster` VIDES,
    `target == owner ==` le PORTEUR de l'effet (d'ou `get_OwnerIsTarget` VRAI sur ce vecteur), et
    c'est `CurrentAbilityIs` -- jamais `TriggeringEffectIs` -- qui porte l'effet retire (#306).

    CONSOMMATEUR (#936) : `WrathfulDevotionAbility` face B
    (`On(0x3b) & get_OwnerIsTarget & CurrentAbilityIs((EffectType)0x40b
    TeleportStrike_TeleportingIn)`) = Wrask qui sort du Deep Strike. AVANT #936 le port n'emettait
    ce vecteur NULLE PART, ce qui rendait inerte tout consommateur -- c'est la raison EXACTE pour
    laquelle `SavageKillerAbility` n'abonne pas sa 4e disjonction (residu #929-r1, desormais
    DEBLOQUE : son `NOT moved` reste a porter, mais le canal existe). No-op si rien ne matche."""
    return _effect_vector_triggers(state, int(EventTriggerType.UnitBecameTargetable),
                                   None, target_id, effect_type, removing=True)


def unit_defeated_triggers(state: State, dying_id: int, killer_id: Optional[int] = None,
                           *, by_flight: bool = False, triggering_ability=None) -> list[dict]:
    """Vecteur `On(UnitDefeated=54=0x36)` (G3) — event NATIF DISTINCT de `PreUnitDeath(1)` : le natif
    `Ambush_SummonAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$CreateTrigger ecoute `On(0x36 = UnitDefeated) & OwnerIsTarget & Not(HasFlag 0xe)`, PAS On(1). Emis
    par le pipeline de mort APRES `after_death_triggers(On 1)` (l'unite est deja alive=False -> l'ability
    fire-on-death voit sa mort). Declenche la pose du decoy Ambush (mort -> decoy) + l'enregistrement de
    `turn_defeated`. No-op si aucun porteur Ambush ne meurt.

    ⚠ **DEUX Operations natives publient cet event, avec des `AbilityEntities` DIFFERENTS** (#947-r1) :

      * `IdunBattle.Operations.KillUnitOperation$$Execute` -- la MORT. Les canaux `killer_id`
        (slot 0x158) et `dying_id` (slot 0x178) sont renseignes ;
      * `IdunBattle.Operations.FleeOperation$$Execute` -- la FUITE, publiee juste APRES
        `On(0x34 = UnitFled)` et a partir de la MEME struct : `actor = caster = triggeringUnit`,
        `target = unit`. La fuyarde n'est PAS morte, donc `by_flight=True` laisse `killer_id` et
        `dying_id` **VIDES** -- les renseigner mentirait sur un mort qui n'existe pas, et
        `AmbushSummonAbility.matches` retombe deja proprement sur `ev.target_id` quand `dying_id`
        est `None`. C'est ce que l'i2 de `HeadClaimer` appelle << defeated >> et non << killed >>."""
    if by_flight:
        actor = int(killer_id) if killer_id is not None else int(dying_id)
        ev = TriggerEvent(EventTriggerType.UnitDefeated, actor, int(dying_id),
                          ranged=False, profile=None, triggering_ability=triggering_ability)
        return evaluate_trigger_operation(state, ev)
    ev = TriggerEvent(EventTriggerType.UnitDefeated,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id)
    return evaluate_trigger_operation(state, ev)


def unit_revived_triggers(state: State, revived_id: int, current_ability=None) -> list[dict]:
    """Vecteur `On(UnitRevived = 0x2d = 45)` (case-89 volet B3) — emis par `ReviveUnitOperation.Execute`
    @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xac1 (`FUN_1800280e0(0x4d, DAT_1831d3468, events, 0x2d)`)  # On(UnitRevived) -- APRES la mutation PV/flags/position
    et **AVANT** la purge de la `ReviveData` (@IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+). DISTINCT d'`On(UnitResurrected=0x2e=46)`
    (`ResurrectUnitOperation`, ambush).

    `current_ability` = le `sourceId` (`AbilityOrEffect`) porte par la `ReviveData` — c'est ce que lit le
    noeud `CurrentAbilityIs` des consommateurs. Consommateurs portes :
      * `PhoenixGem_CanReviveEffect` IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal : `On(0x2d = UnitRevived) & OwnerIsTarget & CurrentAbilityIs(0x5b2=1458
        TriggeredAbilityType.PhoenixGem)` -> `RemoveEffect(marqueur 1451)` = « the FIRST TIME each battle » ;
      * (non porte, cf. residu A2) `FuelledByFury_CanReviveEffect` IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal : meme forme avec
        `CurrentAbilityIs(0x4e3=1251)` -> `DeactivateEffect` (« first time each TURN »).
    Le bras `On(UnitRevived)` du trait Swarm est, lui, re-evalue IMPERATIVEMENT par l'Operation (helper
    `on_group_unit_hp_changed`) — residu structurel deja documente (#60). No-op si rien ne matche."""
    ev = TriggerEvent(EventTriggerType.UnitRevived, revived_id, revived_id,
                      ranged=False, profile=None, ability_type=current_ability)
    return evaluate_trigger_operation(state, ev)


def unit_resurrected_triggers(state: State, resurrected_id: int) -> list[dict]:
    """Vecteur `On(UnitResurrected=0x2e=46)` (G3) — emis par `ResurrectUnitOperation` IdunBattle.Operations.ResurrectUnitOperation$$Execute apres une
    resurrection Ambush (`actor` = l'unite ressuscitee, co-localisee avec le decoy qu'elle vient de crusher).
    Alimente `DecoysAndMisdirection_BuffFriends` (G2, `(On(0x2e = UnitResurrected)|On(0x1d)) & AreFriends` -> +582 + nouveau
    decoy si GS Cult) et la re-arme HeroicFusillade (G5, `On(0x2e = UnitResurrected) & OwnerIsTarget`). No-op si aucun
    consommateur ne matche. Le decoy crushe (steppable, alive=False, meme tuile) satisfait `GetValidDeadDecoys`
    de BuffFriends (co-localisation dead-decoy/stepper)."""
    ev = TriggerEvent(EventTriggerType.UnitResurrected, resurrected_id, resurrected_id,
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)
