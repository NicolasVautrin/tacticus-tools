"""`Abilities.Triggered.Loki.ControlEdictAbility` (passif triggered 1200 de Tan Gi'da / admecMarshall).
Cf. `loki/__init__.py` pour le regroupement « Loki ». RE (verdict re-expert, build gqfc5mff6c) :

  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$CreateTrigger` = `On(0x26=NormalAttack) & OwnerIsCaster & NOT(TriggeringAbilityIs(1024))` :
    APRES une attaque NORMALE de Tan Gi'da (OwnerIsCaster). Le `NOT(TriggeringAbilityIs(1024))` est une garde
    ANTI-RE-TRIGGER (l'attaque induite par un summon ne re-fire pas) ; ici COUVERTE par `matches` (actor==owner)
    -> une attaque de summon (actor=summon != Tan) ne matche pas. Sens exact du 1024 = a confirmer live.
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$CreateBehaviour` = arbre DSL `op_add(If(HasEffect(Protector)), If(HasEffect(Conqueror)))` (2
    branches NON exclusives, gate `HasEffect` sur le caster) :
      * PROTECTOR (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$SummonMinion`) : summon 1 Skitarii Vanguard sur un hex libre ADJACENT AU CASTER,
        cap `maxSummons[level]` (3/4/5), `WithStatsFromConfig`, PAS d'on-appearance. -> Operation
        `SpawnUnitOperation.execute_control_edict_summon` (spawn.py, feuille Spawn du sous-arbre).
      * CONQUEROR (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$AttackWithMinions` + lambda `b__0 IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility.u003Cu003Ec__DisplayClass4_0$$u003CAttackWithMinionsu003Eb__0`) :
        `Foreach(AdjacentFriends(caster) INTER Summon INTER Mechanical, If(IsInAttackRange(summon, target),
        UseActiveAbility(summon, NormalAttackType(summon))))` -> chaque Summon Mechanical adjacent a Tan attaque
        SA cible (celle que Tan vient d'attaquer, `target@0x178`) si a portee, avec son attaque NORMALE.

DOCTRINE #149/slice-24 (== S4a/genestealer) : les predicats/selecteurs S/T (`HasEffect`, `AdjacentFriends`,
`UnitsWithTrait`, `IsInAttackRange`, le cap `AmountIsEqualOrGreater`) sont COLLAPSES imperativement (lecture
d'etat) ; seules les feuilles E (Spawn du summon / attaque normale du summon) delegent aux Operations.
`ControlEditPlaybook IdunBattle.AI.Playbook.Loki.ControlEdictPlaybook$$.ctor` = utility 0 (no-op decisionnel) -> RIEN a enregistrer cote playbook.

GAP flagge (task #25) : le passif `RadSaturation` du Skitarii (contamination sur son hex apres move) n'est
pas porte ici (recon live requise). Le TOUR du Skitarii (move + attaque normale) est joue par le chemin
generique `run_ai_control_pass` (summon_ai.py) -> pas de playbook bespoke (task #24 : verification).

VALIDE (tests/engine/runner/test_control_edict_live.py, 4/4) : LIVE oracle (Tan attaque sous Protector ->
1 Skitarii Vanguard spawn sur sa team ADJACENT a lui, live hp 3878 == build_summon_context @L50x200%) ;
offline Protector (Vanguard adjacent Tan + owner + hp) ; cap maxSummons[level] (no-op au cap) ; offline
Conqueror (Summon Mechanical adjacent attaque la cible a portee + contre-epreuve sans summon)."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, OwnerComponent, PositionComponent, UnitComponent
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from ..base import TriggeredAbility, TriggerEvent, _in_attack_range, _unit_tile
from ...damage import AttackDamageOperation
from ...spawn import SpawnUnitOperation

PROTECTOR = int(EffectType.ProtectorImperative)   # 1247 (0x4df)
CONQUEROR = int(EffectType.ConquerorImperative)    # 1248 (0x4e0)
SUMMON_TRAITS = ("Summon", "Mechanical")           # UnitsWithTrait(Summon=2) INTER UnitsWithTrait(Mechanical=5)


def _adjacent_mechanical_summons(state: State, caster_id: int) -> list:
    """`AdjacentFriends(caster,1,3) |> UnitsWithTrait(Summon=2) |> UnitsWithTrait(Mechanical=5)` (collapse S) :
    ids des amis VIVANTS de `caster`, ADJACENTS (hex, board.neighbours evenq) au caster, portant A LA FOIS les
    traits Summon ET Mechanical (= les Skitarii Vanguards summoned). [] sans board. Tri id (deterministe)."""
    board = state.board
    owner = state.get_entity(caster_id)
    if board is None or owner is None:
        return []
    ooc = owner.get_component(OwnerComponent)
    ot = _unit_tile(state, board, caster_id)
    if ooc is None or ot is None:
        return []
    neigh = set(board.neighbours(ot))
    out: list = []
    for eid, e in state.entities.items():
        if eid == caster_id:
            continue
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        sc = e.get_component(StatsComponent)
        if oc is None or uc is None or sc is None or not uc.alive:
            continue
        if oc.team != ooc.team:                          # amis uniquement
            continue
        t = _unit_tile(state, board, eid)
        if t is None or t not in neigh:                  # adjacents au caster
            continue
        traits = getattr(sc.ctx, "traits", None) or []
        if not all(tr in traits for tr in SUMMON_TRAITS):   # Summon ET Mechanical
            continue
        out.append(eid)
    return sorted(out)


class ControlEdictAbility(TriggeredAbility):
    """`ControlEdictAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$CreateBehaviour) — passif de Tan Gi'da
    (`admecMarshall.passiveAbilities=['ControlEdict']`, triggered id 1200). APRES l'attaque NORMALE de Tan
    (`On(0x26)` & OwnerIsCaster), gate sur l'Imperative ACTIF (etat S4a lu par `HasEffect(caster, 1247/1248)`) :
      - Protector -> summon 1 Skitarii Vanguard adjacent a Tan (cap maxSummons[level]) ;
      - Conqueror -> chaque Summon Mechanical adjacent a Tan attaque la cible de Tan si a portee.
    Les 2 branches (`op_add`) sont NON exclusives (chacune gardee par son `HasEffect`) ; en pratique
    DoctrinaImperatives garantit un seul actif. `matches` (actor==owner) couvre la garde anti-re-trigger.

    ⚠ **`fire_on_death` = VRAI (#10015), et la prose qui disait << owner vivant garanti par le
    dispatch >> etait FAUSSE.** `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility`
    surcharge `IdunBattle.Entities.Abilities.ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` et
    son corps rend VRAI (`b0 01 c3`, LU -- `metadata/allow_for_dead_owner.tsv`) ; le defaut de
    `IdunBattle.Entities.Abilities.BaseTriggeredAbility` est FAUX. Le dispatch natif
    (`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger`) ne garantit donc RIEN
    sur la vie de Tan : si l'attaque normale de Tan le tue (riposte, overwatch, retribution) avant
    la publication d'`On(0x26 = NormalAttack)`, le natif declenche l'Edit et le port ne le faisait
    pas. Le trigger natif ne porte, lui non plus, aucun conjoint de vie du porteur."""
    event_id = int(EventTriggerType.NormalAttack)         # 38 (0x26)
    #: `ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` -> VRAI (cf. la docstring).
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # OwnerIsCaster : Tan est l'attaquant. Une attaque induite (summon) a actor != owner -> pas de re-trigger
        # (= la garde native NOT(TriggeringAbilityIs 1024) pour l'observable).
        return ev.actor_id == self.owner_id

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        eff = state.effects
        if eff is None:
            return None
        prot = eff.has_effect(self.owner_id, effect_type=PROTECTOR)
        conq = eff.has_effect(self.owner_id, effect_type=CONQUEROR)
        if not (prot or conq):
            return None                                   # aucun Imperative actif -> les 2 If sont False
        out: dict = {"ability": "ControlEdict", "owner": self.owner_id, "target": ev.target_id}
        if prot:                                          # If(HasEffect(Protector)) -> SummonMinion
            out["summoned"] = self._summon_minion(state)
        if conq:                                          # If(HasEffect(Conqueror)) -> AttackWithMinions
            out["attacks"] = self._attack_with_minions(state, ev.target_id)
        return out

    def _summon_minion(self, state: State) -> list:
        """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$SummonMinion` -> feuille Spawn (Operation validee)."""
        return SpawnUnitOperation.execute_control_edict_summon(state, self.owner_id)

    def _attack_with_minions(self, state: State, target_id: Optional[int]) -> list:
        """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$AttackWithMinions` + `b__0 IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility.u003Cu003Ec__DisplayClass4_0$$u003CAttackWithMinionsu003Eb__0` : chaque Summon Mechanical adjacent a Tan attaque
        la cible du trigger (`target@0x178`) si `IsInAttackRange`, avec son attaque NORMALE (pipeline normal du
        summon -> selection d'arme Physical melee / Toxic R2 par range). No-op si la cible est absente/morte."""
        if target_id is None:
            return []
        tgt = state.get_entity(target_id)
        tuc = tgt.get_component(UnitComponent) if tgt is not None else None
        if tuc is None or not tuc.alive:
            return []
        results: list = []
        for sid in _adjacent_mechanical_summons(state, self.owner_id):
            if not _in_attack_range(state, sid, target_id):   # If(IsInAttackRange(summon, target, 3))
                continue
            r = AttackDamageOperation.execute(state, sid, target_id)   # UseActiveAbility(summon, NormalAttack)
            results.append({"summon": sid, "attack": r})
        return results
