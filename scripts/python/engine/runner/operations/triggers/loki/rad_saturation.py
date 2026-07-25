"""`Abilities.Triggered.Loki.RadSaturationAbility` (passif triggered 1202 du Skitarii Vanguard
`admecSmnVanguard.passiveAbilities=['RadSaturation']`). Cf. `loki/__init__.py`. RE (decompile ghidra,
build gqfc5mff6c) :

  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RadSaturationAbility$$CreateTrigger` = OU de TROIS branches (op_BitwiseOr) :
      * `On(4=UnitAfterMove) & OwnerIsActor`                 -> APRES que le Skitarii BOUGE lui-meme ;
      * `On(0x23=35=UnitDisplaced) & OwnerIsTarget`          -> quand il est DEPLACE (push/pull) [PORTE, cf. DISPATCH] ;
      * `On(0x17=23=TurnEnd) & OwnerIsActor & NOT(HasFlag moved@0x148)` -> en FIN DE TOUR s'il n'a PAS bouge.
    == i2 `RadSaturation` : « After the Skitarii Vanguard moves, it adds Contamination to its hex. If it does
    not move, then this ability triggers at the end of its turn. »
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RadSaturationAbility$$CreateBehaviour` = feuille UNIQUE `AddEffect(0x4dc=1244=Contaminated, AbilityStateReference,
    selecteur@0x170, 0, 0)`. Le selecteur `@0x170` est passe DIRECTEMENT a AddEffect (SANS wrapper `Tiles()`,
    contrairement a OnFireDamage `Tiles(@0x178=Target)`) => c'est deja un selecteur TILE-DOMAIN = la PROPRE
    tuile du caster (« its hex »). Calibration offsets : `+0x148`=Caster (ControlEdict `HasEffect(Caster)`),
    `+0x178`=Target (OnFire `Tiles(Target)`), `+0x170`=tuile-du-caster. `0` (5e arg) = pas de TurnsFromRounds
    -> `DefaultAmountOfRounds(1244)=2` (effects.py `_DEFAULT_ROUNDS[0x4dc]=2`).

Port = arbre DSL `AddEffect(Contaminated=1244, "Contaminated", Tiles(Caster()))` (mirror 1:1 de la feuille ;
`Tiles(Caster())` = MainTile du caster = sa propre tuile). RadSaturation est le **1er poseur** de l'effet de
TUILE `Contaminated` (1244) du port -- `OnToxicDamageAbility` (1203, l'autre source on-hit Toxic) n'est PAS
porte. La machinerie AVAL est deja portee (`ContaminatedTileEffect` IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateHandleTriggerAbilitiesInternal, effect_triggers.py) : une fois
la tuile porteuse de 1244, elle pose `Contaminated_Unit` (1245, -30% FixedArmor, 1 round, RE #132) sur
l'occupant a l'entree `On(4)` / au tick `On(0x12)`, sauf immunise (ContagionsOfNurgle / Mechanical).

DISPATCH : branche 1 (`On(4)`) via le registre `ABILITY_TRIGGERS` + vecteur `after_move_triggers` (aucun
cablage neuf) ; branche 3 (`On(0x17=TurnEnd)`) via la dispatch generique ajoutee a `end_turn_summon_triggers`
(gate `owner not in state.moved_this_turn`). Branche 2 (`On(0x23=UnitDisplaced) & OwnerIsTarget`) PORTEE via le
vecteur `displace_triggers` (dispatch.py) que `DisplaceUnitOperation.execute` appelle apres le push (mirror
`IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects` : emet On(UnitDisplaced) {actor=pusher,
target=pushed} ; OwnerIsTarget => fire ssi le Skitarii POUSSE est l'owner -> il contamine sa tuile
d'ATTERRISSAGE post-push). RadSaturationPlaybook (utility de move IA vers les tuiles a contaminer) = concern
DECISION separe (non porte ici).

DOCTRINE #149 : predicats/selecteurs du trigger (OwnerIsActor, HasFlag moved) COLLAPSES imperativement
(lecture d'etat) ; la feuille E (`AddEffect` tile-domain) delegue a l'Operation `AddEffectOperation`."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent
from ....abilities.behaviours import AddEffect, entities_from_state
from .....entities.selectors import Tiles, Caster
from .....entities.effect_type import EffectType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

CONTAMINATED_TILE = int(EffectType.Contaminated)          # 1244 (0x4dc) — effet de TUILE (aval = ContaminatedTileEffect)

# Events ecoutes = les TROIS branches du IdunBattleLogic.Entities.Abilities.Triggered.Loki.RadSaturationAbility$$CreateTrigger.
_AFTER_MOVE = int(EventTriggerType.UnitAfterMove)         # 4  — branche 1 (self-move, OwnerIsActor)
_DISPLACED = int(EventTriggerType.UnitDisplaced)          # 35 (0x23) — branche 2 (force-move/push, OwnerIsTarget)
_TURN_END = int(EventTriggerType.TurnEnd)                 # 23 (0x17) — branche 3 (fin de tour si pas bouge)


def rad_saturation_tree():
    """Feuille de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RadSaturationAbility$$CreateBehaviour` (MIRROR 1:1 du DECOMPILE) :
        AddEffect( effectType = 0x4dc=Contaminated (TILE),
                   source     = AbilityStateReference (le caster),
                   target     = <selecteur tile-domain @0x170 = tuile du caster> )
    = un noeud DSL UNIQUE `AddEffect` avec selecteur TILE-DOMAIN `Tiles(Caster())` (== `IdunBattleLogic.Entities.DSLFactory$$Tiles -> MainTile de l'unite ; ici l'unite = le CASTER -> sa propre tuile). La feuille `AddEffect`
    (tile-domain) convertit la position en id de tuile (`_add_effect_target_id`) et route vers
    `AddEffectOperation.execute(target=tile_id, 1244, "Contaminated")`. `duration_rounds=None` = pas de
    TurnsFromRounds (mirror du 5e arg natif `0`) -> `DefaultAmountOfRounds(1244)=2`. RNG-free."""
    return AddEffect(CONTAMINATED_TILE, "Contaminated", Tiles(Caster()), duration_rounds=None)


class RadSaturationAbility(TriggeredAbility):
    """`RadSaturationAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.RadSaturationAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.RadSaturationAbility$$CreateBehaviour) — passif du Skitarii
    Vanguard (`admecSmnVanguard.passiveAbilities=['RadSaturation']`, triggered id 1202). Pose l'effet de TUILE
    `Contaminated` (1244) sur SA PROPRE tuile quand il BOUGE (`On(4) & OwnerIsActor`), quand il est DEPLACE de
    force (`On(0x23=UnitDisplaced) & OwnerIsTarget`, push/pull) ou, s'il n'a PAS bouge ce tour, en FIN DE TOUR
    (`On(0x17=TurnEnd) & OwnerIsActor & NOT moved`). La contamination (aval deja porte `ContaminatedTileEffect`)
    inflige -30% FixedArmor a l'occupant a l'entree/au tick."""
    event_id = _AFTER_MOVE                                 # primaire (branche 1) ; `event_ids` couvre les trois
    event_ids = (_AFTER_MOVE, _DISPLACED, _TURN_END)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.event_id == _AFTER_MOVE:
            # branche 1 : `On(4) & OwnerIsActor` — le Skitarii vient de bouger lui-meme (actor == owner).
            return ev.actor_id == self.owner_id
        if ev.event_id == _DISPLACED:
            # branche 2 : `On(0x23=UnitDisplaced) & OwnerIsTarget` — le Skitarii est FORCE-MOVE (push/pull).
            # L'event porte actor=pusher, target=pushed (mirror `IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects`) ->
            # OwnerIsTarget = fire ssi le Skitarii deplace EST la cible du deplacement (owner == target).
            return ev.target_id == self.owner_id
        if ev.event_id == _TURN_END:
            # branche 3 : `On(0x17) & OwnerIsActor & NOT(HasFlag moved@0x148)` — fin de tour du player courant,
            # le Skitarii n'a PAS bouge ce tour (sinon la branche 1 a deja contamine sa tuile de destination).
            if self.owner_id in state.moved_this_turn:     # NOT(HasFlag moved) : a bouge -> deja couvert
                return False
            owner = state.get_entity(self.owner_id)
            oc = owner.get_component(OwnerComponent) if owner is not None else None
            if oc is None:                                 # OwnerIsActor : owner = unite du player finissant
                return False
            return ev.player_id is None or oc.player == ev.player_id
        return False

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """Behaviour = arbre DSL `rad_saturation_tree()` (mirror 1:1 IdunBattleLogic.Entities.Abilities.Triggered.Loki.RadSaturationAbility$$CreateBehaviour) :
        `AddEffect(Contaminated=1244, Tiles(Caster()))`. La feuille pose l'effet de tuile sur la propre tuile
        du Skitarii ; no-op si la tuile porte deja Contaminated (gate `already-present` d'AddEffect)."""
        if state.effects is None or getattr(state, "board", None) is None:
            return None                                    # pas d'EffectsState/board -> pose impossible
        ectx = ExecutionContext(state=state, rng=state.rng)
        rad_saturation_tree().execute(entities_from_state(state, self.owner_id), ectx)
        placed = [p["target"] for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        if not placed:                                     # tuile deja contaminee -> no-op (anti-repose)
            return None
        return {"passive": "RadSaturation", "unit": self.owner_id,
                "contaminated_tile": placed[0], "on_event": ev.event_id}
