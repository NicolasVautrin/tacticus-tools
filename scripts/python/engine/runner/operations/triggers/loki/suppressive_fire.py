"""`IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility` (triggered id 1044,
accordee par le TRAIT `UnitTrait.SuppressiveFire`=1010, x49 unites dont 8 lineup) — face RUNNER
« pose de Suppressed » : pose l'effet Pinned/« Suppressed » (0x429=1065) sur la cible d'une attaque
RANGED du porteur. RE RE-LUE sur le build `rnca9r7q6c` (#512-r1) :

  - `IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateTrigger` (arbre DSL, conjonction `op_BitwiseAnd`) =
        On(PreAttack=5, ownerNeedsToBeAlive: 1) & IsRangedAttack & get_OwnerIsActor
          & AreEnemies(owner, target)
          & AmountIsGreaterThanZero(Units(target, unique: 1, selectionType: 2))
    = « quand le porteur (actor) fait une attaque a DISTANCE contre un ennemi avec >=1 cible valide ».
  - `IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateBehaviour` (feuille E UNIQUE) =
        AddEffect(0x429=Pinned, source=AbilityStateReference(=owner), cible=Units(target, kind=0),
                  dureeNode=struct ZERO -> DefaultAmountOfRounds)
    `Units` = `UnitsOnTilesSelector` (IdunBattleLogic.Entities.DSLFactory$$Units) : les unites sur les tuiles de la cible
    (positions exclusives -> la cible elle-meme) -> pose Pinned sur l'UNITE cible.
  i2 : « An enemy hit by this unit's ranged attack becomes Suppressed. »

L'effet Pinned (0x429=1065) est DEJA porte (`entities/effects/loki/status.py::PinnedEffect`,
valide live) : stat-mod Movement (`ChangeStat(4, -EffectConfig(1))`) + malus degat ATTAQUANT du
porteur x0.70 (`ForPercentIncrease(OwnerIsCaster, -EffectConfig(0)=PinnedDmgReductionPct=30)`).
Ce port ne RE-porte PAS l'effet — il porte le TRIGGER qui l'applique.

## DISPATCH : `On(PreAttack = 5)`, LE VECTEUR NATIF (#512-r1)

OU LE NATIF EMET `On(5)`, LU AU DECOMPILE (et re-confirme par le nom du slot, jamais par le
voisinage) :

    IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute       # le noeud DSL `Attack(...)`
        caster  = Select(entities+0x50) ; targets = Select(entities+0x58)   (OrderBy si Count > 1)
        for tgt in targets:
            if prev is null or prev != tgt: processor.StartAttack  (slot 58)
            <inner behaviour>                                     # AttackDamage / AbilityDamage
            if next is null or next != tgt: processor.FinishAttack (slot 59)
    IdunBattle.Operations.StartAttackOperation$$Execute
        -> IOperationProcessor.EvaluateAbilitiesImmediately(EventTriggerType.PreAttack = 5,
                                                            AbilityEntities{actor = attaquant,
                                                                            target = la cible})
        (slots LUS dans `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv` :
         58 `StartAttack`/3, 59 `FinishAttack`/3, 80 `EvaluateAbilitiesImmediately`/2 ; la lecture du
         4e argument comme `EventTriggerType` est recoupee sur `ADamageOperation$$
         EvaluateAfterHitTriggers`, qui emet `0x3c = UnitBlocked` puis `8 = AttackHit`.)

-> **`On(5)` part PAR CIBLE DISTINCTE**, avant tout degat. Les trois seuls emetteurs de `StartAttack`
sont `AttackBehaviour$$Execute`, `IdunBattle.Entities.Behaviours.StartAttackBehaviour$$Execute` et
la voie MESSAGE `IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass25_0$$
u003CVisitu003Eb__0`. C'est le MEME etage que le `On(9 = Attack)` de `finish_attack_triggers`
(#437), a l'autre bout de la boucle.

⚠ **CE PORT ECOUTAIT `On(NormalAttack = 38)`, ET LA JUSTIFICATION ECRITE ICI ETAIT FAUSSE.** Elle
disait : « `Attack(9)` fire PAR-CIBLE (splash) alors que le natif suppress la cible PRIMAIRE seule
(PreAttack once) -> sur-suppression des victimes de splash ». La lecture ci-dessus la REFUTE :
`PreAttack` n'est pas « once par attaque », il est **une fois par cible** — donc suppresser chaque
cible d'une attaque multi-cible EST le comportement natif. MESURE (#512, board `MC1_67`,
`emperNoiseMarine` castant `1197`) : la cascade native pose `Pinned` sur les DEUX cibles du rayon,
chacune dans son propre bloc `[Ability_Power e=77 <<SuppressiveFire>>]`, ce qui monte
`TerrifyingCrescendo_ExtraDmg` (0x590) d'un niveau par cible ; le port, muet sur ce vecteur, rendait
`9575 / 7101` contre `10073 / 7766`.

Ce qui reste VRAI de la mise en garde : un SPLASH COMPOSE dans le `Attack(...)` d'une autre attaque
(une feuille `IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage` NUE, `isOutsideAttack = false`,
cf. `#419-r3`) n'ouvre PAS de nouveau `StartAttack`, donc n'emet PAS de `PreAttack` — et le port ne
lui en emet pas non plus (`pre_attack_triggers` est appele par les OPERATIONS d'attaque, une fois
par cible). La distinction est donc STRUCTURELLE (`Attack(...)` vs feuille nue), pas « primaire vs
toutes ».

Gate ranged = `_is_ranged_attack` (mirror COMPLET du slot 3 `IdunBattle.Core.Services.BattleQuery$$
IsRangedAttack`), PAS `ev.ranged` ni `_is_ranged_position` seul :
  - `attackRangeType = Ranged(2)` -> VRAI **sans lire aucune position** (c'est le cas de 1197, et
    c'est ce qui manquait : sa 1re cible est ADJACENTE au caster) ;
  - `Melee(1)` / `None(0)` -> FAUX ;
  - `Normal(3)` ou nom absent (les attaques normales CONCRETES) -> `!AreEntitiesAdjacent`, c.-a-d.
    exactement l'ancien `_is_ranged_position`. Le discriminant melee de la validation live
    (`test_suppressive_fire_live.py` : Pinned a d==2, absent a d==1) EST cette branche-la, donc il
    est preserve. `ev.ranged` reste inutilisable : en voie NORMALE il est weapon-selection-based
    (`select_weapon_pierce` : une unite ranged-ONLY frappant au contact a `ev.ranged=True`).

DOCTRINE #149 : predicats du trigger COLLAPSES imperativement (`matches` : OwnerIsActor + ranged +
AreEnemies + cible presente) ; la feuille E (`AddEffect` unit-domain) delegue a `AddEffectOperation`
(l'effet Pinned impuratif reste porte, status.py). Le `AmountIsGreaterThanZero(Units)` = « la cible
existe » (gate cible presente).

RESIDUS (honnetes) :
- `pre_attack_triggers` n'est PAS emis par la famille de factory ABILITY du port
  (`damage_ops/ability.py`, gate `is_attack_damage_op`). Le natif, LUI, l'emet aussi :
  `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (surcharge racine a 7 arguments)
  finit par `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor(caster, target,
  <AbilityDamageBehaviour>, abilityOrEffect)` — donc par `StartAttack`, donc par `On(5)`. Elargir le
  vecteur reveillerait aussi `LetTheGalaxyBurnArmAbility` (son `Maybe(chance)` consomme un tirage) :
  a confronter live avant de le faire. Residu `#512-r2` (alloue par `probe_468 --suggere 512`).
- `UnitFlag.ForceRangedAttack` (21) n'est publie par aucun capteur (`#419-r1-tr5-r1`) : la branche
  `Normal(3)` ne le lit pas. Degradation RESTRICTIVE (le natif rendrait ranged sans regarder
  l'adjacence), nommee."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from .....entities.selectors.accessors import Target
from .....entities.effect_type import EffectType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _is_ranged_attack

PINNED = int(EffectType.Pinned)                   # 1065 (0x429) — UI « Suppressed »
_ON_PRE_ATTACK = int(EventTriggerType.PreAttack)  # 5 — LE vecteur natif (cf. header, #512-r1)


def suppressive_fire_tree():
    """Feuille de `IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateBehaviour` (MIRROR 1:1 du DECOMPILE) :
        AddEffect( effectType = 0x429=Pinned,
                   source     = AbilityStateReference (== owner ; triggered Owner==Caster),
                   cible      = Units(Target@0x178) = l'UNITE cible touchee )
    `duration_rounds=None` = pas de TurnsFromRounds (mirror du struct duree ZERO natif) ->
    `DefaultAmountOfRounds(0x429)` (== Pinned de SentinelDirectives/SpiritLeech/CrushingClaws).
    `Target()` (unit-domain) resout la cible en dict d'unite -> `AddEffectOperation` la pose sur
    l'unite (contraste `Tiles(Target())` d'AddIce = tile-domain)."""
    return AddEffect(PINNED, "Pinned", Target(), duration_rounds=None)


class SuppressiveFireAddEffectAbility(TriggeredAbility):
    """`SuppressiveFireAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateBehaviour) — triggered
    1044 accorde par le TRAIT `SuppressiveFire` (1010). Pose Pinned/« Suppressed » (1065) sur la
    cible d'une attaque a DISTANCE du porteur (`On(PreAttack = 5)`, OwnerIsActor, IsRangedAttack,
    AreEnemies). L'effet Pinned lui-meme = `PinnedEffect` (status.py, deja porte+valide)."""
    event_id = _ON_PRE_ATTACK

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
        # `IsRangedAttack` = mirror COMPLET du slot 3 `IdunBattle.Core.Services.BattleQuery$$
        # IsRangedAttack` : `Ranged(2)` -> vrai SANS lire la position ; `Melee(1)`/`None(0)` -> faux ;
        # `Normal(3)` (et nom absent = attaque normale concrete) -> `!AreEntitiesAdjacent`. PAS
        # `ev.ranged`, qui est weapon-selection-based sur la voie normale (cf. header).
        return _is_ranged_attack(state, ev.ability_type, ev.actor_id, ev.target_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """Behaviour = arbre DSL `suppressive_fire_tree()` (mirror 1:1 IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateBehaviour) :
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
