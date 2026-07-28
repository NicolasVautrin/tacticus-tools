"""Revive-EN-PLACE d'unite -- sous-systeme `ReviveData` (case-66 / #88-#89). DISTINCT de
`ResurrectUnitOperation` (ambush tile-choice, resurrect.py) : le REVIVE remet l'unite VIVANTE a la MEME
position (in-place) ; il n'y a PAS de tuile choisie ni de flag one-shot Ambush.

--------------------------------------------------------------------------------------------------
LE PIVOT : `UnitComponent + 0xa8` = `Nullable<ReviveData>` (case-89 volet C, RE 2026-07-25)
--------------------------------------------------------------------------------------------------
La feuille DSL `Revive` NE MUTE RIEN. Le sous-systeme est en DEUX TEMPS, articules autour du champ
`Nullable<ReviveData>` @UnitComponent+0xa8 :

  1. POSE      `IdunBattleLogic.Entities.DSLFactory$$Revive` -> `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute` : pour chaque
               cible du selecteur, `amount = Min(formule, IdunBattle.Entities.Behaviours.ReviveBehaviour$$GetMaxReviveAmount)`, construit la
               `ReviveData` puis, SI `IdunBattle.Entities.Behaviours.ReviveBehaviour$$IsPreferredRevive`, ECRIT les 9 qwords
               `unitComponent + 0xa8 .. +0xe8`. AUCUNE mutation de PV/flag/position ici.
  2. GARDE     `IdunBattle.Operations.KillUnitOperation$$Execute` : `On(1)` est emis @IdunBattle.Operations.KillUnitOperation$$Execute+0x7dc PUIS
               @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e la garde `pcVar21 = thunk_FUN_1801f3000(unitComponent + 0xa8,
               <hasValue de Nullable<ReviveData>>) ; if (*pcVar21 == '\\0') { ... }`. TOUT le reste de
               la mort est DANS ce bloc (verifie a la profondeur d'accolades : `On(1)` @depth 7,
               `On(2)`/`On(0)`/`On(55)`/`On(54)` @depth 9). Un revive POSE pendant `On(1)`
               **ANNULE la mort** -- cf. `damage.py::_fire_death_if_killed`.
  3. DRAIN     `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` lance DEUX phases : `RunPhase(0xc)`
               (les kills, lambda `<VerifyDeaths>b__0 IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass49_0$$u003CVerifyDeathsu003Eb__0` -> `KillUnit` slots 0x60/0x61) PUIS
               `RunPhase(0xd)` sur la 2e liste de requete -> `Core.Services.OperationProcessor$$ReviveUnit`
               -> `IdunBattle.Operations.ReviveUnitOperation$$Execute` (ICI) qui LIT la `ReviveData`, applique, et
               REMET LES 9 QWORDS A 0 @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+.

Le port COLLAPSE 2+3 au meme endroit (`kill_unit_revive_gate`, appelee par `_fire_death_if_killed`
juste apres `On(1)`) : c'est l'ordre observable natif (la phase 0xd suit la phase 0xc).

--------------------------------------------------------------------------------------------------
`IdunBattle.Operations.ReviveUnitOperation$$Execute` (mutateur ECS IMPERATIF, mirror ci-dessous)
--------------------------------------------------------------------------------------------------
  * garde        @IdunBattle.Operations.ReviveUnitOperation$$Execute+0x2ba : `if (!pendingRevive.HasValue)` -> `Logger.Error` + RETURN (pas de revive)
  * IdunBattle.Operations.ReviveUnitOperation$$SetHealth : hp = Min(ReviveData.amount, GetStat(unit, Health=5, MAX=3))  (re-clamp)
  * flags        IdunBattle.Operations.ReviveUnitOperation$$Execute+0x7e0 : Remove(0xf), Remove(8=overkill), Add(0x14) -> l'unite redevient VIVANTE
                 (PAS 0xe AmbushConsumed -- un revive-en-place N'EST PAS un ambush one-shot)
  * IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition : repositionne sur la tuile de l'unite -> IN-PLACE
  * emet `On(UnitRevived = 46 = 0x2e)` @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xac1 (`FUN_180026490(0x4d,...,lVar16,0x2e)`)
  * PUIS purge `unitComponent + 0xa8 .. +0xe8 = 0` @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+ (donc APRES le dispatch de On(0x2e))

Frontiere DSL (#149) : la feuille `Revive` (declaratif, `triggers/revive_effect.py`) POSE ; l'Operation
(imperatif, ICI) APPLIQUE. On NE fusionne PAS.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import UnitComponent, HealthComponent

# `Revive(..., healType, sourceId, ?, priority, ?)` -- priorite par defaut des consommateurs
# (`IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour` et `FuelledByFury_ReviveAbility.CreateBehaviour
# IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility$$CreateBehaviour` passent 0 ; `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour` passe **-1000**
# = 0xfffffc18, la plus BASSE -> tout autre revive lui est prefere).
REVIVE_PRIORITY_DEFAULT = 0


def is_preferred_revive(existing: Optional[dict], new: dict) -> bool:
    """`IdunBattle.Entities.Behaviours.ReviveBehaviour$$IsPreferredRevive` (mirror 1:1) :

        if (!existing.HasValue) return true;                       // aucun revive en attente
        if (new.priority > existing.priority) return true;         // param_3[6] vs local_30
        if (new.priority < existing.priority) return false;
        return existing.amount < new.amount;                       // local_48[0] < *param_3

    (Le decompile teste `param_3[6] <= local_30` puis `local_30 <= param_3[6]` : le premier `if` filtre
    `new.priority > existing.priority` -> true ; l'egalite retombe sur la comparaison des `amount`.)"""
    if existing is None:
        return True
    ep, np_ = int(existing.get("priority") or 0), int(new.get("priority") or 0)
    if np_ > ep:
        return True
    if np_ < ep:
        return False
    return int(existing.get("amount") or 0) < int(new.get("amount") or 0)


def post_pending_revive(state: State, unit_id: int, amount, heal_type: int = 0,
                        source=None, priority: int = REVIVE_PRIORITY_DEFAULT,
                        revive_position=None) -> Optional[dict]:
    """Mirror de l'ECRITURE de `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute` : pose la `ReviveData` sur
    `unitComponent + 0xa8` si `IsPreferredRevive`. AUCUNE mutation de PV/flag/position (c'est
    `ReviveUnitOperation` qui les fait, plus tard). Renvoie la `ReviveData` posee, ou None si le gate
    `IsPreferredRevive` l'a rejetee (ou entite/composant absent).

    `source` = le `sourceId` (`Nullable<AbilityOrEffect>`) : `AbilityOrEffect(effect.Id)` pour un
    `ReviveEffect` (IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour `param_1[2]`), `AbilityOrEffect(this.Id)` pour une TriggeredAbility
    autonome (PhoenixGem 1458 IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour, FuelledByFury 1251 IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility$$CreateBehaviour). Il est relu par le noeud
    `CurrentAbilityIs` des triggers `On(UnitRevived)`.

    `revive_position` = le champ `Nullable<UnitPosition>` de la `ReviveData` (#213). Il est renseigne
    par `ReviveBehaviour$$Execute` UNIQUEMENT quand le 7e argument de `IdunBattleLogic.Entities.
    DSLFactory$$Revive` (`targetsTile`) est NON NUL : le decompile evalue alors ce selecteur
    (`FUN_180024d10(10, …, param_2+0x90, entities)`), en prend l'element d'index de la CIBLE COURANTE
    (`IList.get_Item(i)`), le `ToList()` et l'enveloppe dans le `Nullable`. Tous les consommateurs
    portes AVANT #213 passent `targetsTile = 0` -> `None` = revive **IN-PLACE** (c'est le
    `if (!revivePosition.HasValue) return;` en tete de
    `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition`). Le SEUL poseur non-nul du build
    est `IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTriggerBehaviour` (`tiles =
    Owner@0x148` = la TUILE porteuse du ghost). Le port collapse la `UnitPosition` (liste de tuiles,
    une par pied) en un `(col, row)` -- meme collapse que `PositionComponent`."""
    e = state.get_entity(unit_id)
    if e is None:
        return None
    uc = e.get_component(UnitComponent)
    if uc is None:
        return None
    data = {"amount": (None if amount is None else int(amount)), "heal_type": int(heal_type),
            "source": source, "priority": int(priority),
            "revive_position": (None if revive_position is None
                                else (int(revive_position[0]), int(revive_position[1])))}
    if not is_preferred_revive(uc.pending_revive, data):
        return None
    uc.pending_revive = data
    return data


def _set_revive_position(state: State, unit_id: int, pos) -> Optional[tuple]:
    """`IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition(revivePosition, unit)` -- MIRROR.

    C'est le SEUL endroit du sous-systeme revive ou la POSITION change, et la garde qui l'ouvre est
    la premiere instruction de la fonction :

        if (!revivePosition.HasValue) return;              <- revive IN-PLACE (cas par defaut)
        pos      = revivePosition.Value
        feet     = UnitExtensions.GetUnitFeet(unit)        \\
        ResetPreviousTileIfStillOwned(unit, feet)           > liberation des tuiles occupees
        ResetFeet(unit)                                    /
        newTiles = BattleQuery.<slot 0x8d>(pos)
        processor.<slot 0x7e = MoveUnit>(unit, pos, false)  <- ECRITURE de la position
        KillSteppableUnits(unit, newTiles)                  <- ce qui trainait sur la tuile est ecrase
        AbilityEntities.ctor(unit, unit, unit, …, feet, …, pos, …)
        publie On(0x24 = UnitPositionChanged_1)
        publie On(0x1d = UnitPositionChanged_2)

    Le port n'a ni entites-pieds ni reservation de tuile -> `ResetPreviousTileIfStillOwned`/`ResetFeet`
    n'ont pas d'equivalent observable (la position exclusive du port suffit : ecrire la nouvelle tuile
    libere l'ancienne). Le reste est porte tel quel : ecriture de `PositionComponent`, crush des
    Steppable de la tuile d'arrivee (MEME helper que le move, `movement._kill_steppable_units`), puis
    les DEUX events de position.

    ⚠ `On(0x24)` est precisement l'un des cinq retraits de `GhostEffect` (« une autre unite arrive sur
    la tuile du ghost ») : une resurrection sur un ghost peut donc en retirer un AUTRE. Le ghost sur
    lequel on ressuscite, lui, s'est deja retire par son propre `GetRemoveEffectBehaviour`.

    Renvoie la position ecrite, ou `None` si le revive est resté in-place (garde native)."""
    if pos is None:
        return None                                   # `if (!revivePosition.HasValue) return;`
    e = state.get_entity(unit_id)
    if e is None:
        return None
    from ..components import PositionComponent
    to = (int(pos[0]), int(pos[1]))
    pc = e.get_component(PositionComponent)
    if pc is None:
        e.add_component(PositionComponent(to[0], to[1]))
    else:
        pc.col, pc.row = to
    # `KillSteppableUnits(unit, newTiles)` -- MEME operation que celle du move (helper partage, pas
    # une 2e implementation) : un decoy/spore-mine sur la tuile d'arrivee est ecrase par un kill
    # PROPRE (aucun death-trigger).
    from .movement import _kill_steppable_units
    _kill_steppable_units(state, to, unit_id)
    # `On(0x24 = UnitPositionChanged_1)` puis `On(0x1d = UnitPositionChanged_2)`, {actor = target =
    # l'unite ressuscitee} (`AbilityEntities.ctor(unit, unit, unit, …)` lu au decompile).
    from .triggers import unit_position_changed_1_triggers, unit_position_changed_2_triggers
    unit_position_changed_1_triggers(state, unit_id)
    unit_position_changed_2_triggers(state, unit_id)
    return to


class ReviveUnitOperation:
    """Mirror `IdunBattle.Operations.ReviveUnitOperation$$Execute` (mutateur ECS, revive-EN-PLACE). Signature NATIVE
    = `Execute(operation, entity)` : le HP n'est PAS un parametre, il vient de la `ReviveData` posee sur
    `UnitComponent + 0xa8` (mirror exact ici). `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` re-clampe `Min(amount, hp_max)`.
    Position INCHANGEE (in-place)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: int) -> Optional[dict]:
        e = state.get_entity(unit_id)
        if e is None:
            return None
        uc = e.get_component(UnitComponent)
        if uc is None:
            return None
        data = uc.pending_revive
        if data is None:
            # @IdunBattle.Operations.ReviveUnitOperation$$Execute+0x2ba : `if (!pendingRevive.HasValue)` -> Logger.Error + RETURN (aucun revive).
            return None
        hc = e.get_component(HealthComponent)
        hp = data.get("amount")
        # IdunBattle.Operations.ReviveUnitOperation$$SetHealth : hp = Min(amount, GetStat(unit, Health, MAX)). Sans HealthComponent/max
        # capte -> on pose l'amount brut (fidelite-safe : le clamp natif est un Min, jamais un boost).
        set_hp = None
        if hc is not None and hp is not None:
            set_hp = int(hp)
            if hc.hp_max is not None:
                set_hp = min(set_hp, int(hc.hp_max))     # Min(amount, maxHP)
            hc.hp = set_hp
        # flags IdunBattle.Operations.ReviveUnitOperation$$Execute+0x7e0 : Remove(0xf), Remove(8=overkill), Add(0x14) -> l'unite redevient VIVANTE.
        # Le port modelise l'etat de vie via `uc.alive` (les flags ECS 0xf/0x14 = internes non suivis) ;
        # `Remove(8)` est PORTE depuis que `UnitFlag.Overkilled` est materialise (pose par le pipeline de
        # degat, lu par `HasFlag(unit, 8)` du volet OVERKILL de DoomSiren) -- sans lui, une unite revive
        # apres overkill (TaintedNarthecium `ReviveOnOverkill`) resterait marquee overkillee.
        # ENREGISTREMENT `HasBeenRevivedByAbility` (#213) : mirror du bloc que le natif execute
        # ENTRE `SetHealth` et les flags -- `if (sourceId.HasValue) { GetComponent<
        # ActorStatisticsComponent>(unit)@+0xe0 .Add(sourceId.Value) }`. C'est CE set que relit
        # `HasBeenRevivedAbilityTrigger$$ShouldTrigger`, et il n'est JAMAIS remis a zero : le gate
        # `NOT HasBeenRevivedByAbility(self, 1186)` de `GhostReviveAbility`/`GhostEffect` est donc un
        # « une seule fois par BATAILLE ». Loge sur le `UnitComponent` du port (residu structurel
        # documente, cf. `components.py`).
        src = data.get("source")
        if src is not None:
            uc.revived_by_abilities.add(int(src))
        from ..components import UnitFlagsComponent
        fl = e.get_component(UnitFlagsComponent)
        if fl is not None:
            fl.remove(UnitFlagsComponent.OVERKILLED)
        uc.alive = True
        # IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition : appele ICI (apres les flags,
        # AVANT `On(0x2e)`). Le natif sort immediatement si `revivePosition` n'a pas de valeur -> le
        # revive est alors IN-PLACE (aucune ecriture de position), ce qui est le cas de TOUS les
        # consommateurs sauf le ghost de `thousTerminator` (#213).
        moved_to = _set_revive_position(state, unit_id, data.get("revive_position"))
        # #60 : re-eval du stat-mod EXTRA_HITS du trait Swarm au retour a la vie (bras On(UnitRevived=46) du
        # IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger), comme ResurrectUnitOperation.
        if hc is not None and set_hp is not None:
            from ..abilities.loki.swarm import on_group_unit_hp_changed
            on_group_unit_hp_changed(state, unit_id)
        # `On(UnitRevived = 0x2e = 46)` @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xac1 -- emis AVANT la purge du champ (ordre natif lu).
        # Consommateurs portes : `PhoenixGem_CanReviveEffect` (IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal : retrait du marqueur 1451 sous
        # `CurrentAbilityIs(PhoenixGem)`), et tout futur `On(0x2e)`.
        from .triggers import unit_revived_triggers
        fired = unit_revived_triggers(state, unit_id, current_ability=data.get("source"))
        # purge des 9 qwords @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+ : la `ReviveData` est consommee.
        uc.pending_revive = None
        return {"revived": int(unit_id), "hp": set_hp, "in_place": moved_to is None,
                "revive_position": moved_to,
                "source": data.get("source"), "on_revived": fired}


def kill_unit_revive_gate(state: State, unit_id: int) -> Optional[dict]:
    """**GARDE de `KillUnitOperation.Execute` @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e** + DRAIN de la phase `RunPhase(0xd)` de
    `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`, fondus (le port collapse le pump FIFO natif, cf. `dispatch.py`).

    A appeler JUSTE APRES `On(PreUnitDeath = 1)` et AVANT `On(PreUnitDeath_2 = 2)` :
      * renvoie `None`  -> `pendingRevive.HasValue == false` : la garde PASSE, la mort CONTINUE
        (le caller emet `On(2)`, `On(0)`, `On(55)`, `On(54)` et fait le bookkeeping de mort) ;
      * renvoie un dict -> un revive etait EN ATTENTE : la garde ECHOUE, **toute la suite de la mort est
        COURT-CIRCUITEE** cote natif ; on applique ici le revive (mirror `ReviveUnitOperation.Execute`)
        et le caller DOIT s'arreter."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or uc.pending_revive is None:
        return None                                     # garde franchie -> la mort suit son cours
    return ReviveUnitOperation.execute(state, unit_id)   # phase 0xd : le revive est applique


def reset_revive_gates(state: State) -> None:
    """Debut de tour -> REACTIVE le passif revive (remet `revive_used_this_turn=False` pour TOUTES les
    unites). Mirror de la RE-ACTIVATION au turn-start de l'effet `ReviveEffect` desactive par `DeactivateEffect`
    apres un revive reussi (i2 « Can only be triggered once per turn »). Meme patron que `reset_times_attacked`
    (per-unite, per-tour). Appele par `start_turn_triggers`."""
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        if uc is not None:
            uc.revive_used_this_turn = False
