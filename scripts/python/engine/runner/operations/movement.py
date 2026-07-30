"""Operations de mouvement — `IdunBattle.Operations.MoveUnitOperation` IdunBattle.Operations.MoveUnitOperation$$Execute.

Tranche 1, INCRÉMENT 1a (POSITION) : écrit la position finale du mover dans son
`PositionComponent`. C'est le cœur observable du move (le natif fait aussi la
validation, CalculatePaths, AddMoveEvent/pas, charging…, mais l'EFFET d'ÉTAT sur
le mover = sa position finale).

G1 (gen-stealer) : `IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` PORTÉ ici (`_kill_steppable_units`),
INLINE dans l'ordre natif (avant `EvaluateAfterMoveTriggers`) — un occupant Steppable
(decoy/spore-mine) de la tuile d'arrivée est crushé (kill propre, sans death-trigger).

INCRÉMENT 1b (à venir, validé vs la vérité-terrain probe = Maugan Ra 1174 sur le
mover) : `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers → cascade OVERWATCH
(`Overwatch_AutoAttackEffect` → auto-attaque → dégât + consommation de l'effet).
`IdunBattle.Operations.MoveUnitOperation$$AddMoveEvent émet l'event UnitMoved(step 3) + tuiles du chemin sur le bus.
"""
from __future__ import annotations

from ..state import State
from ..events import EventBus
from ..components import (PositionComponent, UnitComponent, StatsComponent, HealthComponent,
                          set_moved_flag, update_charging)
from .base import Operation


def _kill_steppable_units(state: State, dest_tile: tuple[int, int], mover_id: int) -> list:
    """`MoveUnitOperation$$IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` — étape INLINE du move pipeline (avant
    `EvaluateAfterMoveTriggers`). Quand une unité MOVE sur `dest_tile`, tout occupant `Steppable`
    (`IdunBattle.Entities.UnitExtensions$$IsSteppable` = `HasTrait(0x1b=27)`) VIVANT y est détruit par un kill **propre**
    (`KillUnitOperationOptions$$IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable`, type=2 flags 0x0101) : `alive=False` (hp 0) SANS
    passer par `after_death_triggers`/`On(1)` — un decoy/spore-mine crushé ne déclenche donc PAS les
    death-triggers de combat (ex. l'Ambush du decoy — cf. G3). `mover_id` est exclu (une unité ne se crushe
    pas elle-même). Renvoie les ids crushés. Ordre natif : `AddMoveEvent` → **KillSteppableUnits** →
    `EvaluateAfterMoveTriggers` (d'où le decoy déjà mort quand DecoysAndMisdirection lit `GetValidDeadDecoys`,
    G2)."""
    from ...entities.traits import UnitTrait, has_trait
    killed: list = []
    for uid, e in list(state.entities.items()):
        if uid == mover_id:
            continue
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or uc is None or not uc.alive:
            continue
        if (pc.col, pc.row) != dest_tile:
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], UnitTrait.Steppable):
            continue
        uc.alive = False                              # kill PROPRE (ForSteppable) : PAS de after_death_triggers
        hc = e.get_component(HealthComponent)
        if hc is not None:
            hc.hp = 0
        killed.append(uid)
    return killed


class MoveUnitOperation(Operation):
    """IdunBattle.Operations.MoveUnitOperation$$Execute (1a) — pose la position finale du mover. `to` = (col,row).

    `set_moved` = mirror de l'octet `+0x11` du `MoveUnitOptions` natif (5e argument d'`Execute`,
    struct passee par valeur) : le decompile fait
    `if (*(options + 0x11) == 0) UnitExtensions.SetMovedFlag(unit);`. Il vaut donc `True` (flag pose)
    pour TOUS les call-sites qui passent des options nulles -- c'est-a-dire tous ceux du port SAUF
    `SwitchPositionOperation`, dont le `DisplaceUnitOperation$$SwitchPosition` natif passe un
    `MoveUnitOptions` NON nul.
    MESURE qui tranche (probe_287, `combatSnapshot.units[].unitFlags` AVANT/APRES le cast de 1100) :
    le caster TELEPORTE par le switch gagne `[ArrivedAtFinalTile, ActiveAbilityUsed, TurnFinished,
    NoActionAvailable]` et **PAS `Moved`**. Un port qui poserait `Moved` ici fermerait a tort la
    regle `CasterHasNotMoved` (0x10) de tout cast ulterieur du meme tour."""
    __slots__ = ("unit_id", "to", "set_moved")

    def __init__(self, unit_id: int, to: tuple[int, int], set_moved: bool = True):
        self.unit_id = unit_id
        self.to = to
        self.set_moved = bool(set_moved)

    def execute(self, state: State, bus: EventBus) -> None:
        e = state.get_entity(self.unit_id)
        if e is None:
            return
        # `On(PreUnitMove = 0x1f = 31)` — EMIS EN TETE, avant TOUTE mutation. Place native lue au
        # decompile d'`IdunBattle.Operations.MoveUnitOperation$$Execute` : le corps
        # d'`EvaluatePreMoveTriggers` y est INLINE juste apres `SetReservation` et **avant**
        # `CalculatePaths`/`MoveUnit`/`AddMoveEvent`/`KillSteppableUnits`/`UpdateCharging`/
        # `SetMovedFlag`/`EvaluateAfterMoveTriggers` -> l'unite est ENCORE sur sa tuile de depart.
        # Consommateurs : `GhostReviveAbility` (pose du time-ghost) + le 1er retrait de `GhostEffect`
        # (le poseur rebouge). No-op si aucun trigger ne matche.
        from .triggers import pre_move_triggers
        pre_move_triggers(state, self.unit_id)
        pc = e.get_component(PositionComponent)
        old_pos = (pc.col, pc.row) if pc is not None else None
        if pc is None:
            e.add_component(PositionComponent(self.to[0], self.to[1]))
        else:
            pc.col, pc.row = self.to
        # #198 : materialisation DYNAMIQUE du stat-mod DEFENSE de tuile (Thorns/famille). En quittant/
        # entrant une tuile a stat-mod DEFENSE, l'occupant non-Immune gagne/perd la modification (mirror
        # ThornsDefenseReductionEffect apply-on-enter/revert-on-leave). No-op hors terrain a stat-mod /
        # sans board / Immune. On saute un ajout d'entite (pc None = spawn, pas un move de tuile-a-tuile).
        if old_pos is not None:
            from .triggers.tiles import apply_tile_defense_on_move
            apply_tile_defense_on_move(state, self.unit_id, old_pos, self.to)
        # G1 (gen-stealer) `IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` : INLINE ici, dans l'ordre natif (AddMoveEvent ->
        # **KillSteppableUnits** -> EvaluateAfterMoveTriggers). Un occupant Steppable (decoy, spore-mine) de la
        # tuile d'arrivée est crushé (kill propre, pas de death-trigger) AVANT que le vecteur after-move
        # (visit_MoveUnitMessage -> after_move_triggers) ne s'exécute -> le decoy est déjà mort pour G2.
        _kill_steppable_units(state, self.to, self.unit_id)
        # `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` — RANG NATIF EXACT (le decompile
        # d'`IdunBattle.Operations.MoveUnitOperation$$Execute` l'appelle entre `KillSteppableUnits` et
        # `SetMovedFlag`). Enregistre sur le mover les unites NOUVELLEMENT adjacentes apres ce pas :
        # c'est la moitie runtime du predicat `BattleQuery$$IsCharging` (TacticalPrecision, case-231).
        # `old_pos is None` (unite sans position avant : spawn) -> mirror du `MainTile == null` natif.
        update_charging(state, self.unit_id, old_pos, self.to)
        # #101 : `SetMovedFlag(unit)` — le natif pose ici le `UnitFlag.Moved` (+ `Teleported` si le move
        # est un teleport-strike). POSITION NATIVE lue au decompile d'`IdunBattle.Operations.
        # MoveUnitOperation$$Execute` : AddMoveEvent(s) -> KillSteppableUnits -> UpdateCharging ->
        # **SetMovedFlag** (gate par l'option `MoveUnitOptions` @+0x8, nulle a tous les call-sites du
        # port -> flag TOUJOURS pose) -> Add(ArrivedAtFinalTile=1) [non porte] -> after-move triggers.
        # C'est LE store unique du fait "a bouge ce tour" (lu par `unit_has_moved`), purge par le
        # `RemoveTurnFlags` du StartTurnOperation. (#60 posait un set `state.moved_this_turn` PARALLELE
        # au composant natif -> fork de port : deux representations du meme flag, l'une jamais posee par
        # le move, l'autre jamais lue par le gate no-move.)
        # ⚠ Le gate `MoveUnitOptions+0x11` du natif est desormais MODELISE (`set_moved`, cf. le ctor) :
        # le seul call-site qui le pose est `SwitchPositionOperation` (mesure live #287).
        if self.set_moved:
            set_moved_flag(state, self.unit_id)
        # AURA stat-mod PROJETEE — `UpdateEffectTargets` : le selecteur d'un `AStatModifierEffect` a
        # projection est purement GEOMETRIQUE, donc un move le change. Le natif re-evalue et
        # applique/reverte la `ValueModification` chez les cibles. GROUND TRUTH live (statModSources,
        # LionHelm) : l'allie eloigne PERD ses +797 blockDamage, il les RETROUVE en revenant.
        # No-op strict sans porteur d'aura stat-mod (le mover ET les cibles du porteur sont re-evalues,
        # d'ou l'appel non scope : bouger le PORTEUR change l'ensemble de ses cibles).
        from .aura_stat_mods import refresh_aura_stat_modifiers
        refresh_aura_stat_modifiers(state)
        # `RefreshEffectTrigger.UnitPositionChanged` (= 7, dump d'enums du build : 0=Forced
        # 1=Simulation 2=Custom 3=UnitStateChanged 4=EffectsChanged 5=UnitsChanged 6=TurnChanged
        # **7=UnitPositionChanged** 8=MatchStart) -> `IdunBattle.Operations.RefreshEffectsOperation
        # $$Execute` avec un `effectEntity` NUL, c'est-a-dire sur TOUS les effets de la bataille :
        # chacun voit sa `CreateActiveCondition` reevaluee par
        # `RefreshEffectsOperation$$ShouldBeActive`, et bascule ACTIVE <-> INERTE avec
        # `ApplyModification`/`RevertModification` a la cle.
        # C'est le volet PORTEUR de la meme donnee que `refresh_aura_stat_modifiers` juste au-dessus
        # (celui-la couvre les stat-mods PROJETES, dont le selecteur est geometrique ; celui-ci les
        # stat-mods poses SUR une unite dont la CONDITION est geometrique). Cas porte :
        # `ContagionsOfNurgle_ArmorReduction1/2` — un pas qui fait entrer/sortir du disque d'aura
        # ennemi fait entrer/sortir le -20 %/-40 % de `FixedArmor`.
        # Non-scope (pas de `unit_id`) POUR LA MEME RAISON que la ligne precedente : bouger le
        # PORTEUR d'aura change la condition des AUTRES unites, pas la sienne. Idempotent partout
        # ailleurs (`Modify` = replace par-source, cf. `refresh_effects.py`).
        from .refresh_effects import refresh_stat_modifier_effects
        refresh_stat_modifier_effects(state)
        # INCRÉMENT 1b : AddMoveEvent (bus) + EvaluateAfterMoveTriggers (overwatch) ici.


class MovementHandler:
    """Visiteur des messages de mouvement (mirror du handler natif qui lance
    MoveUnitOperation). Lié à l'état/bus du runner. `after_move` = résultats du vecteur after-move
    (effet-triggers ; ex. Overwatch) du dernier move."""
    __slots__ = ("state", "bus", "after_move")

    def __init__(self, state: State, bus: EventBus):
        self.state = state
        self.bus = bus
        self.after_move: list = []          # cascade after-move (overwatch…) du dernier move

    def visit_MoveUnitMessage(self, msg) -> None:
        MoveUnitOperation(msg.unit_id, msg.to).execute(self.state, self.bus)
        # VECTEUR AFTER-MOVE : dispatcher générique (mirror `EvaluateAfterMoveTriggers`). Déclenche les
        # effet-triggers after-move (Overwatch…). No-op si pas de board/rng ou aucun trigger en portée.
        from .triggers import after_move_triggers
        self.after_move = after_move_triggers(self.state, msg.unit_id)
