"""Revive-EN-PLACE d'unite -- sous-systeme `ReviveData` (case-66 / #88-#89). DISTINCT de
`ResurrectUnitOperation` (ambush tile-choice, resurrect.py) : le REVIVE remet l'unite VIVANTE a la MEME
position (in-place) ; il n'y a PAS de tuile choisie ni de flag one-shot Ambush.

--------------------------------------------------------------------------------------------------
LE PIVOT : `UnitComponent + 0xa8` = `Nullable<ReviveData>` (case-89 volet C, RE 2026-07-25)
--------------------------------------------------------------------------------------------------
La feuille DSL `Revive` NE MUTE RIEN. Le sous-systeme est en DEUX TEMPS, articules autour du champ
`Nullable<ReviveData>` @UnitComponent+0xa8 :

  1. POSE      `DSLFactory.Revive @180dfa4f0` -> `ReviveBehaviour.Execute @180fd1230` : pour chaque
               cible du selecteur, `amount = Min(formule, GetMaxReviveAmount @180fd1a80)`, construit la
               `ReviveData` puis, SI `IsPreferredRevive @180fd1b50`, ECRIT les 9 qwords
               `unitComponent + 0xa8 .. +0xe8`. AUCUNE mutation de PV/flag/position ici.
  2. GARDE     `KillUnitOperation.Execute @180e76470` : `On(1)` est emis @0x180e76c4c PUIS
               @0x180e76c9e la garde `pcVar21 = thunk_FUN_1801f3000(unitComponent + 0xa8,
               <hasValue de Nullable<ReviveData>>) ; if (*pcVar21 == '\\0') { ... }`. TOUT le reste de
               la mort est DANS ce bloc (verifie a la profondeur d'accolades : `On(1)` @depth 7,
               `On(2)`/`On(0)`/`On(55)`/`On(54)` @depth 9). Un revive POSE pendant `On(1)`
               **ANNULE la mort** -- cf. `damage.py::_fire_death_if_killed`.
  3. DRAIN     `InputMessageProcessor.VerifyDeaths @180ebb0a0` lance DEUX phases : `RunPhase(0xc)`
               (les kills, lambda `<VerifyDeaths>b__0 @180ecb870` -> `KillUnit` slots 0x60/0x61) PUIS
               `RunPhase(0xd)` sur la 2e liste de requete -> `OperationProcessor.ReviveUnit @180e0b510`
               -> `ReviveUnitOperation.Execute @180e91bd0` (ICI) qui LIT la `ReviveData`, applique, et
               REMET LES 9 QWORDS A 0 @0x180e92977+.

Le port COLLAPSE 2+3 au meme endroit (`kill_unit_revive_gate`, appelee par `_fire_death_if_killed`
juste apres `On(1)`) : c'est l'ordre observable natif (la phase 0xd suit la phase 0xc).

--------------------------------------------------------------------------------------------------
`ReviveUnitOperation.Execute @180e91bd0` (mutateur ECS IMPERATIF, mirror ci-dessous)
--------------------------------------------------------------------------------------------------
  * garde        @0x180e91e8a : `if (!pendingRevive.HasValue)` -> `Logger.Error` + RETURN (pas de revive)
  * SetHealth    @180e93450 : hp = Min(ReviveData.amount, GetStat(unit, Health=5, MAX=3))  (re-clamp)
  * flags        @180e923b0 : Remove(0xf), Remove(8=overkill), Add(0x14) -> l'unite redevient VIVANTE
                 (PAS 0xe AmbushConsumed -- un revive-en-place N'EST PAS un ambush one-shot)
  * SetRevivePosition @180e936e0 : repositionne sur la tuile de l'unite -> IN-PLACE
  * emet `On(UnitRevived = 46 = 0x2e)` @0x180e92691 (`FUN_180026490(0x4d,...,lVar16,0x2e)`)
  * PUIS purge `unitComponent + 0xa8 .. +0xe8 = 0` @0x180e92977+ (donc APRES le dispatch de On(0x2e))

Frontiere DSL (#149) : la feuille `Revive` (declaratif, `triggers/revive_effect.py`) POSE ; l'Operation
(imperatif, ICI) APPLIQUE. On NE fusionne PAS.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import UnitComponent, HealthComponent

# `Revive(..., healType, sourceId, ?, priority, ?)` -- priorite par defaut des consommateurs
# (`ReviveEffect.CreateTargetTriggerBehaviour @180f46a70` et `FuelledByFury_ReviveAbility.CreateBehaviour
# @180f810c0` passent 0 ; `PhoenixGem_ReviveAbility.CreateBehaviour @181111610` passe **-1000**
# = 0xfffffc18, la plus BASSE -> tout autre revive lui est prefere).
REVIVE_PRIORITY_DEFAULT = 0


def is_preferred_revive(existing: Optional[dict], new: dict) -> bool:
    """`ReviveBehaviour.IsPreferredRevive @180fd1b50` (mirror 1:1) :

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
                        source=None, priority: int = REVIVE_PRIORITY_DEFAULT) -> Optional[dict]:
    """Mirror de l'ECRITURE de `ReviveBehaviour.Execute @180fd1230` : pose la `ReviveData` sur
    `unitComponent + 0xa8` si `IsPreferredRevive`. AUCUNE mutation de PV/flag/position (c'est
    `ReviveUnitOperation` qui les fait, plus tard). Renvoie la `ReviveData` posee, ou None si le gate
    `IsPreferredRevive` l'a rejetee (ou entite/composant absent).

    `source` = le `sourceId` (`Nullable<AbilityOrEffect>`) : `AbilityOrEffect(effect.Id)` pour un
    `ReviveEffect` (@180f46a70 `param_1[2]`), `AbilityOrEffect(this.Id)` pour une TriggeredAbility
    autonome (PhoenixGem 1458 @181111610, FuelledByFury 1251 @180f810c0). Il est relu par le noeud
    `CurrentAbilityIs` des triggers `On(UnitRevived)`."""
    e = state.get_entity(unit_id)
    if e is None:
        return None
    uc = e.get_component(UnitComponent)
    if uc is None:
        return None
    data = {"amount": (None if amount is None else int(amount)), "heal_type": int(heal_type),
            "source": source, "priority": int(priority)}
    if not is_preferred_revive(uc.pending_revive, data):
        return None
    uc.pending_revive = data
    return data


class ReviveUnitOperation:
    """Mirror `ReviveUnitOperation.Execute @180e91bd0` (mutateur ECS, revive-EN-PLACE). Signature NATIVE
    = `Execute(operation, entity)` : le HP n'est PAS un parametre, il vient de la `ReviveData` posee sur
    `UnitComponent + 0xa8` (mirror exact ici). `SetHealth @180e93450` re-clampe `Min(amount, hp_max)`.
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
            # @0x180e91e8a : `if (!pendingRevive.HasValue)` -> Logger.Error + RETURN (aucun revive).
            return None
        hc = e.get_component(HealthComponent)
        hp = data.get("amount")
        # SetHealth @180e93450 : hp = Min(amount, GetStat(unit, Health, MAX)). Sans HealthComponent/max
        # capte -> on pose l'amount brut (fidelite-safe : le clamp natif est un Min, jamais un boost).
        set_hp = None
        if hc is not None and hp is not None:
            set_hp = int(hp)
            if hc.hp_max is not None:
                set_hp = min(set_hp, int(hc.hp_max))     # Min(amount, maxHP)
            hc.hp = set_hp
        # flags @180e923b0 : Remove(0xf), Remove(8=overkill), Add(0x14) -> l'unite redevient VIVANTE.
        # Le port modelise l'etat de vie via `uc.alive` (les flags ECS 0xf/8/0x14 = internes non suivis).
        uc.alive = True
        # SetRevivePosition @180e936e0 : IN-PLACE -> position inchangee (aucune ecriture de PositionComponent).
        # #60 : re-eval du stat-mod EXTRA_HITS du trait Swarm au retour a la vie (bras On(UnitRevived=46) du
        # SwarmAbility.CreateTrigger @181225f50), comme ResurrectUnitOperation.
        if hc is not None and set_hp is not None:
            from ..abilities.loki.swarm import on_group_unit_hp_changed
            on_group_unit_hp_changed(state, unit_id)
        # `On(UnitRevived = 0x2e = 46)` @0x180e92691 -- emis AVANT la purge du champ (ordre natif lu).
        # Consommateurs portes : `PhoenixGem_CanReviveEffect` (@180f5e4a0 : retrait du marqueur 1451 sous
        # `CurrentAbilityIs(PhoenixGem)`), et tout futur `On(0x2e)`.
        from .triggers import unit_revived_triggers
        fired = unit_revived_triggers(state, unit_id, current_ability=data.get("source"))
        # purge des 9 qwords @0x180e92977+ : la `ReviveData` est consommee.
        uc.pending_revive = None
        return {"revived": int(unit_id), "hp": set_hp, "in_place": True,
                "source": data.get("source"), "on_revived": fired}


def kill_unit_revive_gate(state: State, unit_id: int) -> Optional[dict]:
    """**GARDE de `KillUnitOperation.Execute` @0x180e76c9e** + DRAIN de la phase `RunPhase(0xd)` de
    `VerifyDeaths @180ebb0a0`, fondus (le port collapse le pump FIFO natif, cf. `dispatch.py`).

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
