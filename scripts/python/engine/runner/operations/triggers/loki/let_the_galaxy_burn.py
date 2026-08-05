"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility` + son
`LetTheGalaxyBurn_ResetAbility` (triggered 0x5ca=1482, accordee par le TRAIT `UnitTrait
.LetTheGalaxyBurn` 0x422=1058 -- les 5 heros Black Legion blackAbaddon / blackHaarken /
blackObliterator / blackPossession / blackTerminator) : le VOLET 1 du kit = **l'armement du coup
additionnel**.

⚠ HOMONYMIE (piege documente) : `ActiveAbilityType.Waaagh` vaut AUSSI 1058. Les espaces `UnitTrait`,
`TriggeredAbilityType`, `ActiveAbilityType` et `EffectType` sont INDEPENDANTS -- ici 1058 = UnitTrait,
1482 = TriggeredAbilityType, 1477 = EffectType (l'owner-effect `LetTheGalaxyBurnEffect`),
1476 = EffectType `DespoiledGround` (le volet 2, tile-effect).

## RE (decompile ghidra, build gqfc5mff6c)

| Symbole | VA |
|---|---|
| `LetTheGalaxyBurnAbility$$CreateTrigger`            | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` |
| `LetTheGalaxyBurnAbility$$CreateBehaviour`          | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateBehaviour` |
| `LetTheGalaxyBurnAbility$$TargetHasTileEffect`      | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$TargetHasTileEffect` |
| `LetTheGalaxyBurnAbility$$.cctor`                   | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$.cctor` |
| `LetTheGalaxyBurn_ResetAbility$$CreateBehaviour`    | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour` |
| `LetTheGalaxyBurnEffect$$.ctor`                     | `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$.ctor` |
| `LetTheGalaxyBurnEffect$$CreateAdditionalHits`      | `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` |
| `DSLFactory$$IsPersistentData`                      | `IdunBattleLogic.Entities.DSLFactory$$IsPersistentData` |
| `DSLFactory$$HasTileStatusEffect`                   | `IdunBattleLogic.Entities.DSLFactory$$HasTileStatusEffect` |

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` (conjonction `AbilityTrigger.op_BitwiseAnd`)
```
On(5=PreAttack, 1, 0) & get_OwnerIsCaster
                      & Maybe( ConfigConst(0x2a, config) )
                      & !HasTileStatusEffect( Targets@0x190 )
```
`ConfigConst 0x2a` = le slot CHANCE generique (meme slot que le 30 % de `GetStuckInAbility
.IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance`) ; l'ability `LetTheGalaxyBurn` n'existant PAS dans `units.abilities`,
il est seede depuis les vars de trait -> `traitVariables.LetTheGalaxyBurnChancePct` = **33**
(meme mecanique que Camouflage/Diminutive/Parry).

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateBehaviour` (feuille E unique)
```
SetPersistentData( AbilityOrEffect(0x5ca=1482), Self@0x148,
                   Get(<champ statique pose par le .IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$.cctor>), Direct(1)@0xc0 )
```
= arme un FLAG intra-attaque sur le porteur, lu par `IsPersistentData` dans le gate du coup.

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour` (`AbilityBehaviour.op_Addition`)
```
  If( IsPersistentData(0x5ca, Self@0x148, Get(<statique>)) & AttackUsedAttackDamage,
      Foreach( Targets@0x190,
               If( !HasTileStatusEffect(Current@0x180),
                   AddEffect(0x5c4=1476 DespoiledGround, AbilityStateReference,
                             source=Self@0x148, cible=Current@0x180, options ZERO) ) ) )
+ ClearPersistentData( AbilityOrEffect(0x5ca), Self@0x148, Get(<statique>) )
```
Le `ClearPersistentData` est **hors du If** -> INCONDITIONNEL. Le volet `AddEffect(1476)` = le
**volet 2** (pose de Despoiled Ground) -- **NON porte ici** (residu explicite, cf. bas de docstring).

## Gate `HasTileStatusEffect` : GENERIQUE et EXCLUSIF
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$TargetHasTileEffect` = `HasTileStatusEffect(Targets@0x190)` : n'importe quel status-effect
de tuile (pas un type precis). Le trigger de POSE exige `!HasTileStatusEffect(...)`, tandis que le gate
du COUP (`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`) accepte `TargetHasTileEffect | IsPersistentData`. Les deux
branches sont donc EXCLUSIVES :
  - cible **hors** tuile a effet -> le coup ne part que si le roll 33 % a arme le flag ;
  - cible **sur** tuile a effet  -> le coup part TOUJOURS, et rien n'est pose.

GROUND TRUTH LIVE (`probe_84_ltgb_chance.py`, blackTerminator vs bloodSanguinary, board MC1_67, 8
runners) : branche A n=73 -> 25 attaques a 5 coups contre 4 de base = **34.2 %** (== 33 % config) ;
branche B n=23 -> **23/23** a 5 coups. Le +1 est exactement correle a l'apparition de
`DespoiledGround` sur la tuile de la cible (volet 2, natif).

## DISPATCH (port)
- POSE : `On(PreAttack=5)`, emis par `pre_attack_triggers` (dispatch.py) **AVANT** le calcul du nb de
  coups dans les vecteurs d'attaque -- exactement la position native (le natif emet PreAttack avant
  `GetAttackHits`, sinon le flag ne pourrait pas etre lu par le canal de la MEME attaque).
- CLEAR : `On(Attack=9)`, le vecteur fin-d'attaque deja emis par le port pour la normale ET les
  abilities (`FinishAttackOperation IdunBattle.Operations.FinishAttackOperation$$Execute`). **HYPOTHESE** : le `CreateTrigger` du
  `LetTheGalaxyBurn_ResetAbility` est un corps DEDUPLIQUE (absent de la table des symboles) -> le
  vecteur exact n'est pas lu au decompile ; `On(9)` est le seul evenement fin-d'attaque generique
  (normale + ability) du port, et le behaviour teste `AttackUsedAttackDamage` (= post-degat), ce qui
  le contraint a cette famille. Flagge comme tel.

## RESIDUS (honnetes)
- **Volet 2 non porte** : `AddEffect(0x5c4=1476 DespoiledGround)` sur les tuiles des cibles (avec son
  effet 1478 `DespoiledGround_ExtraDamagePct`). Consequence OFFLINE : la branche B du gate ne
  s'auto-alimente pas (aucun DespoiledGround n'apparait offline) -- elle reste atteignable par tout
  AUTRE tile-effect (Fire/Ice/Contaminated...) et par le contexte LIVE threade.
- **Ordre de conso RNG : RESOLU (O4a)**. Le natif place `Maybe` AVANT `!HasTileStatusEffect` dans la
  conjonction (`MultipleAbilityTrigger$$ShouldTrigger` = gauche puis droite) ; le port l'evalue
  desormais DANS CET ORDRE, avec la primitive du natif (`MaybeTrigger` -> `NextBool(chance)`, borne
  99). Ce qui a change, mesurable : (a) un tirage est consomme meme quand la cible est deja sur une
  tuile a status-effect (branche B), alors que l'ancien port n'en consommait AUCUN ; (b) le verdict
  d'un meme etat MT peut differer -- l'ancien port tirait `next_internal(0, 100) < 33` (33/100, borne
  100) la ou le natif fait `next_internal(1, 100) <= 33` (33/99).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import PositionComponent, PersistentDataComponent
from ....abilities.behaviours import entities_from_state
from .....entities.effects.loki.hits import LET_THE_GALAXY_BURN_PERSISTENT_KEY
from .....entities.effects.magnitude import trait_var
from .....entities.triggers import MaybeTrigger
from .....dsl.base import Const
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent
from ....damage_model import tile_status_effects_by_pos

_ON_PRE_ATTACK = int(EventTriggerType.PreAttack)   # 5  — vecteur de POSE (avant le calcul des coups)
_ON_ATTACK = int(EventTriggerType.Attack)          # 9  — vecteur fin-d'attaque (CLEAR)


def _target_tile_effects(state: State, target_id: Optional[int]) -> list:
    """`IdunBattleLogic.Entities.DSLFactory$$HasTileStatusEffect(Targets@0x190) cote runner : les status-effects DYNAMIQUES
    portes par la TUILE de la cible (`state.effects.by_unit[tile_entity_id]`). MEME lecture que le
    contexte threade dans la formule de coups (`damage_model.tile_status_effects_by_pos`) -> le trigger
    de POSE et le gate du COUP voient exactement le meme etat. Board/effets/position absents -> []."""
    if target_id is None:
        return []
    e = state.get_entity(target_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is None:
        return []
    tfx = tile_status_effects_by_pos(state, [(pc.col, pc.row)])
    return list((tfx or {}).get((pc.col, pc.row)) or ())


def _persistent(state: State, owner_id: int) -> Optional[PersistentDataComponent]:
    """Get-or-create le `PersistentDataComponent` du porteur (mirror : le natif l'a d'office)."""
    e = state.get_entity(owner_id)
    if e is None:
        return None
    c = e.get_component(PersistentDataComponent)
    if c is None:
        c = PersistentDataComponent()
        e.add_component(c)
    return c


class LetTheGalaxyBurnArmAbility(TriggeredAbility):
    """`LetTheGalaxyBurnAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateBehaviour) — arme le flag
    persistant 1482 sur le porteur, au `On(PreAttack=5)` de SON attaque, avec 33 % de chance, et
    SEULEMENT si la cible n'est PAS deja sur une tuile a status-effect."""
    event_id = _ON_PRE_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:               # get_OwnerIsCaster (le porteur EST l'attaquant)
            return False
        if ev.target_id is None or state.get_entity(ev.target_id) is None:
            return False
        # ORDRE NATIF (O4a) : la conjonction est `((On(5) & OwnerIsCaster) & Maybe(chance))
        # & !HasTileStatusEffect(Targets@0x190)`, et `IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger`
        # evalue GAUCHE puis (si vrai) DROITE. Le `Maybe` passe donc AVANT le gate de tuile : le tirage
        # est consomme meme quand la cible est deja sur une tuile a status-effect (pose impossible).
        pct = trait_var("LetTheGalaxyBurn", "LetTheGalaxyBurnChancePct")
        # `Maybe(ConfigConst 0x2a)` -> `MaybeTrigger` : `NextBool(chance)` (== `next_internal(1,100)
        # <= chance`, borne 99), PAS `next_internal(0,100) < chance` (borne 100) — primitive du natif.
        ents = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        if not MaybeTrigger(state.rng, Const(int(pct or 0))).should_trigger(ents):
            return False
        # !HasTileStatusEffect(Targets@0x190) : gate EXCLUSIF -- deja sur une tuile a effet => pas de pose
        # (le coup partira quand meme, par l'autre branche du gate de `CreateAdditionalHits`).
        return not _target_tile_effects(state, ev.target_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateBehaviour` = `SetPersistentData(0x5ca, Self@0x148, Get(<statique>),
        Direct(1)@0xc0)` -> pose la cle composite `(1482, "LetTheGalaxyBurn")` a la valeur 1."""
        c = _persistent(state, self.owner_id)
        if c is None:
            return None
        c.persist_data(LET_THE_GALAXY_BURN_PERSISTENT_KEY, 1)
        return {"trait": "LetTheGalaxyBurn", "unit": int(self.owner_id),
                "armed": True, "target": int(ev.target_id)}


class LetTheGalaxyBurnResetAbility(TriggeredAbility):
    """`LetTheGalaxyBurn_ResetAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour) — la moitie PORTEE du reset :
    `ClearPersistentData(0x5ca, Self@0x148, Get(<statique>))`, INCONDITIONNEL (hors du `If`), a la fin
    de l'attaque du porteur. Le volet `AddEffect(0x5c4=1476 DespoiledGround)` du meme behaviour est le
    VOLET 2 -- non porte (residu explicite, cf. entete du module)."""
    event_id = _ON_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return ev.actor_id == self.owner_id            # OwnerIsCaster (fin de SON attaque)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        c = _persistent(state, self.owner_id)
        if c is None:
            return None
        had = LET_THE_GALAXY_BURN_PERSISTENT_KEY in c.data
        c.clear_persistent_data(LET_THE_GALAXY_BURN_PERSISTENT_KEY)
        return {"trait": "LetTheGalaxyBurn", "unit": int(self.owner_id), "cleared": bool(had)}
