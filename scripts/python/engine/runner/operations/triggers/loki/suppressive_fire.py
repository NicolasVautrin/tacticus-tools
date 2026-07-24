"""`IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility` (triggered id 1044,
accordee par le TRAIT `UnitTrait.SuppressiveFire`=1010, x49 unites dont 8 lineup) — face RUNNER
« pose de Suppressed » : pose l'effet Pinned/« Suppressed » (0x429=1065) sur la cible d'une attaque
RANGED du porteur. RE (decompile ghidra, build gqfc5mff6c) :

  - `CreateTrigger @181225d00` (arbre DSL, conjonction `op_BitwiseAnd`) =
        On(PreAttack=5) & IsRangedAttack & get_OwnerIsActor
          & AreEnemies(owner@0x148, target@0x178)
          & AmountIsGreaterThanZero(Units(target@0x178, kind=2))
    = « quand le porteur (actor) fait une attaque a DISTANCE contre un ennemi avec >=1 cible valide ».
  - `CreateBehaviour @181225c50` (feuille E UNIQUE) =
        AddEffect(0x429=Pinned, source=AbilityStateReference(=owner), cible=Units(target@0x178, kind=0),
                  dureeNode=struct ZERO -> DefaultAmountOfRounds)
    `Units` = `UnitsOnTilesSelector` (@180e01340) : les unites sur les tuiles de `target@0x178`
    (positions exclusives -> la cible elle-meme) -> pose Pinned sur l'UNITE cible.
  i2 : « An enemy hit by this unit's ranged attack becomes Suppressed. »

L'effet Pinned (0x429=1065) est DEJA porte (`entities/effects/loki/status.py::PinnedEffect`,
valide live) : stat-mod Movement (`ChangeStat(4, -EffectConfig(1))`) + malus degat ATTAQUANT du
porteur x0.70 (`ForPercentIncrease(OwnerIsCaster, -EffectConfig(0)=PinnedDmgReductionPct=30)`).
Ce port ne RE-porte PAS l'effet — il porte le TRIGGER qui l'applique.

DISPATCH : vecteur `after_hit_normal_attack` (`On(NormalAttack=38)`, actor=porteur,
target=cible primaire). Le natif ecoute `On(PreAttack=5)` (emis AVANT le degat, UNE fois par
attaque, cible primaire) ; le port n'emet pas de vecteur PreAttack — on route sur `On(38)` (emis
UNE fois par attaque NORMALE, cible primaire, y compris pour un tir Blast dont le splash est en
sous-operation sans NormalAttack). OBSERVABLE IDENTIQUE : Suppressed pose sur la cible primaire
d'une attaque ranged, independamment du timing avant/apres degat (l'effet Pinned n'affecte PAS le
degat ENTRANT ; il ne borne que le mouvement + le degat FUTUR du porteur suppresse). Cf. residus.

Gate ranged = POSITION-based (`_is_ranged_position` = mirror `DSLFactory.IsRangedAttack @180df4d90`,
= non-adjacent), PAS `ev.ranged` : en voie NORMALE `ev.ranged` est weapon-selection-based
(`select_weapon_pierce` : une unite ranged-ONLY frappant un ennemi ADJACENT a `ev.ranged=True`
alors que IsRangedAttack=False = melee de position). Le natif gate sur la POSITION -> une unite a
arme ranged qui frappe au contact NE suppress PAS (= le discriminant melee de la validation).

DOCTRINE #149 : predicats du trigger COLLAPSES imperativement (`matches` : OwnerIsActor + ranged +
AreEnemies + cible presente) ; la feuille E (`AddEffect` unit-domain) delegue a `AddEffectOperation`
(l'effet Pinned impuratif reste porte, status.py). Le `AmountIsGreaterThanZero(Units)` = « la cible
existe » (gate cible presente).

RESIDUS (honnetes) :
- Attaques d'ABILITY ranged : le natif `On(PreAttack=5)` est GENERIQUE (normale ET ability) ; ce
  port ne cable que `On(38)` (attaque normale). Un carrier qui suppress via une ATTAQUE-ABILITY
  ranged ne serait pas couvert -> extensible en ajoutant `Attack(9)` a `event_ids` MAIS `Attack(9)`
  fire PAR-CIBLE (splash) alors que le natif suppress la cible PRIMAIRE seule (PreAttack once) ->
  sur-suppression des victimes de splash. NormalAttack(38) evite ce piege ET couvre le 100% des 8
  carriers (attaque normale ranged). Aucun scenario de validation ne l'exige.
- Cible tuee par l'attaque : le port fire APRES le degat (vecteur after-hit) ; le natif fire AVANT
  (PreAttack). On pose Pinned meme si la cible vient de mourir (== convention LordOfTempests
  `AddIce` : « meme si le coup l'a tuee ») — no-op observable (un cadavre Suppressed n'agit pas)."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent
from ....abilities.behaviours import AddEffect, entities_from_state
from .....entities.selectors import Target
from .....entities.effect_type import EffectType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _is_ranged_position

PINNED = int(EffectType.Pinned)                   # 1065 (0x429) — UI « Suppressed »
_ON_NORMAL = int(EventTriggerType.NormalAttack)   # 38 (0x26) — vecteur de dispatch (cf. header)


def suppressive_fire_tree():
    """Feuille de `SuppressiveFireAbility.CreateBehaviour @181225c50` (MIRROR 1:1 du DECOMPILE) :
        AddEffect( effectType = 0x429=Pinned,
                   source     = AbilityStateReference (== owner ; triggered Owner==Caster),
                   cible      = Units(Target@0x178) = l'UNITE cible touchee )
    `duration_rounds=None` = pas de TurnsFromRounds (mirror du struct duree ZERO natif) ->
    `DefaultAmountOfRounds(0x429)` (== Pinned de SentinelDirectives/SpiritLeech/CrushingClaws).
    `Target()` (unit-domain) resout la cible en dict d'unite -> `AddEffectOperation` la pose sur
    l'unite (contraste `Tiles(Target())` d'AddIce = tile-domain)."""
    return AddEffect(PINNED, "Pinned", Target(), duration_rounds=None)


class SuppressiveFireAddEffectAbility(TriggeredAbility):
    """`SuppressiveFireAbility` (CreateTrigger @181225d00 / CreateBehaviour @181225c50) — triggered
    1044 accorde par le TRAIT `SuppressiveFire` (1010). Pose Pinned/« Suppressed » (1065) sur la
    cible d'une attaque a DISTANCE du porteur (`On(38)`, OwnerIsActor, IsRangedAttack POSITION-based,
    AreEnemies). L'effet Pinned lui-meme = `PinnedEffect` (status.py, deja porte+valide)."""
    event_id = _ON_NORMAL

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:                  # get_OwnerIsActor (le porteur EST l'attaquant)
            return False
        if ev.target_id is None:
            return False
        tgt = state.get_entity(ev.target_id)              # AmountIsGreaterThanZero(Units) : cible presente
        if tgt is None:
            return False
        owner = state.get_entity(self.owner_id)
        oc = owner.get_component(OwnerComponent) if owner is not None else None
        tc = tgt.get_component(OwnerComponent)
        if oc is None or tc is None or oc.team == tc.team:   # AreEnemies(owner, target)
            return False
        # IsRangedAttack (POSITION-based, mirror @180df4d90) : non-adjacent = ranged (PAS ev.ranged).
        return _is_ranged_position(state, ev.actor_id, ev.target_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """Behaviour = arbre DSL `suppressive_fire_tree()` (mirror 1:1 @181225c50) :
        `AddEffect(Pinned=1065, Target())`. Target() = la cible de l'evenement (l'ennemi touche) ;
        source = le porteur (caster, triggered Owner==Caster)."""
        if state.effects is None:
            return None                                    # pas d'EffectsState -> pose impossible
        if ev.target_id is None or state.get_entity(ev.target_id) is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        suppressive_fire_tree().execute(
            entities_from_state(state, self.owner_id, ev.target_id), ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        return {"trait": "SuppressiveFire", "unit": self.owner_id,
                "suppressed": ev.target_id, "placed": bool(placed), "on_event": ev.event_id}
