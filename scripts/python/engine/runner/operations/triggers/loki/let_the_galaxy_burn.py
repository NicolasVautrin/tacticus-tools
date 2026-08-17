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
| `DSLTriggers$$IsPersistentData`                      | `IdunBattleLogic.Entities.DSLTriggers$$IsPersistentData` |
| `IdunBattleLogic.Entities.DSLTriggers$$HasTileStatusEffect`                   | `IdunBattleLogic.Entities.IdunBattleLogic.Entities.DSLTriggers$$HasTileStatusEffect` |

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
RELU sur `rnca9r7q6c` (#BL-1029r-r1) -- les offsets de `DSLSelectors` ont bouge de `-0x118` entre
`gqfc5mff6c` et ce build (`Owner` 0x148->0x30, `Caster` 0x160->0x48, `Target` 0x178->0x60,
`Current` 0x180->0x68, `TargetTiles` 0x190->0x78) :
```
  If( IsPersistentData(0x5ca, Owner@DSLSelectors+0x30, DSLFormulas.Get(<statique>))
      & AttackUsedAttackDamage,
      Foreach( TargetTiles@DSLSelectors+0x78,
               If( !HasTileStatusEffect(Current@DSLSelectors+0x68),
                   AddEffect(0x5c4=1476 DespoiledGround, AbilityStateReference,
                             source=Owner@+0x30, cibles=Current@+0x68, options ZERO) ) ) )
+ ClearPersistentData( AbilityOrEffect(0x5ca), Owner@+0x30, DSLFormulas.Get(<statique>) )
```
Le `ClearPersistentData` est **hors du If** -> INCONDITIONNEL, et il vient APRES le volet 2 dans
l'`op_Addition` : le flag doit donc etre LU avant d'etre efface.

⚠ **Le selecteur du `Foreach` est `TargetTiles`, PAS `Targets`** -- cette docstring ecrivait
`Targets@0x190`, et c'etait FAUX. Trois lectures concordantes le tranchent :
(a) `IdunBattle.Operations.AddEffectOperation$$Execute` ne route RIEN : il pose l'effet sur son
    parametre `owner` tel quel (il teste meme `EntityExtensions$$IsUnit(owner)` -- le domaine est
    MIXTE unite/tuile) ; un `Foreach` sur des unites poserait donc l'effet sur l'UNITE ;
(b) le meme slot `+0x190` (gqfc) est deja lu `TargetTiles` par un port valide --
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour`
    = `AddEffect(5 Fire, stateRef, TargetTiles@0x190)` ;
(c) MESURE LIVE (`probe_bl1029r_r1_despoiled_ground.py`, seed 777, `MC1_67`) : apres le cast, la
    TUILE de la cible porte `['Melta_ExtraDmg', 'DespoiledGround']` et l'UNITE cible porte
    `['RelentlessMarch_DangerZone']` -- l'effet est sur la tuile, pas sur l'unite.
L'i2 du trait le dit aussi : « add Despoiled Ground **to the hex** of the attacked unit ».

Le volet `AddEffect(1476)` = le **volet 2**, PORTE depuis #BL-1029r-r1 (cf. `_despoil_target_tile`).

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

## VOLET 2 -- PORTE (#BL-1029r-r1), et il n'etait pas cosmetique
`AddEffect(0x5c4=1476 DespoiledGround)` sur la TUILE de chaque cible. Tant qu'il manquait, la
branche B du gate du coup (`TargetHasTileEffect`) ne s'auto-alimentait JAMAIS offline : la 2e
attaque d'une meme chaine repassait par le `Maybe(33 %)` la ou le natif avait deja rendu le coup
CERTAIN. MESURE qui l'etablit (`probe_bl1029r_r1_despoiled_ground.py`, seed 777, `MC1_67`, cast de
`Drachnyen` sur `blackAbaddon`) -- la cascade LIVE, dans l'ordre :
```
  [29] coup 1507   (coup additionnel LetTheGalaxyBurn de l'attaque NORMALE, flag arme)
  [31] group src=LetTheGalaxyBurn
  [32] group src=DespoiledGround        <-- POSE, a la CLOTURE de l'attaque normale
  [38] group src=Drachnyen_ExtraAttack  <-- l'extra attack demarre APRES
  [40][43][46] coups 4092 / 1265 / 1303
  [49] coup 1297 + [51] group src=LetTheGalaxyBurn   <-- le 10e coup, par la branche B
```
L'ordre natif qui rend cela possible est LU, pas suppose :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteBehaviour` appelle
`$$ExecuteNormalAttack` (qui contient le `FinishAttack` -> `On(9)` -> CE reset) **puis**
`$$ExecuteTriggerAbilities` (`EvaluateAbilities(0x26 = NormalAttack)` -> la triggered 1485). Le port
respecte deja cet ordre (`abilities/behaviours/combat.py::UseActiveAbility`).

## RESIDUS (honnetes)
- **Effet 1478 `DespoiledGround_ExtraDamagePct` non porte** (le bonus de degat que la tuile despoilee
  confere), ni le DoT de tuile `EnvDespoiledGroundTileDamage` -- LIVE, le tick de fin de tour inflige
  a l'occupant `Effect_Type: 1476` (mesure : 35188 sur une cible a 500000 PV forces). Poser l'effet ne
  les active PAS cote port (aucun `TileEffectTrigger` n'est enregistre pour 1476) : c'est une
  divergence PREEXISTANTE, ni creee ni aggravee ici, mais desormais ATTEIGNABLE offline puisque la
  tuile porte l'effet.
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
from ....abilities.behaviours.context import entities_from_state
from .....entities.effect_type import EffectType
from .....entities.effects.loki.hits import LET_THE_GALAXY_BURN_PERSISTENT_KEY
from .....entities.effects.magnitude import trait_var
from .....entities.triggers import MaybeTrigger
from .....dsl.base import Const
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent
from ....damage_model import tile_status_effects_by_pos
# FORME B (`import <module>` puis `<module>.<nom>`) : un binding de module n'est jamais gele, donc un
# `monkeypatch.setattr("engine.runner.operations.effects.AddEffectOperation", ...)` mord. Import EN
# TETE et non differe : classe GRATUIT (mesure -- charger `engine.runner.operations.effects` seul en
# process frais ne tire PAS ce module-ci), donc aucun cycle a fermer.
from ... import effects as _ops_effects

_ON_PRE_ATTACK = int(EventTriggerType.PreAttack)   # 5  — vecteur de POSE (avant le calcul des coups)
_ON_ATTACK = int(EventTriggerType.Attack)          # 9  — vecteur fin-d'attaque (CLEAR)


def _target_tile_effects(state: State, target_id: Optional[int]) -> list:
    """`IdunBattleLogic.Entities.DSLTriggers$$HasTileStatusEffect(Targets@0x190) cote runner : les status-effects DYNAMIQUES
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


def _despoil_target_tile(state: State, owner_id: int, target_id: Optional[int]) -> Optional[int]:
    """Corps du `Foreach` du volet 2 :
    `If(!HasTileStatusEffect(Current@DSLSelectors+0x68), AddEffect(0x5c4 = 1476 DespoiledGround,
    AbilityStateReference, source = Owner@+0x30, cibles = Current@+0x68, options ZERO))`.

    L'element courant est une TUILE (le selecteur du `Foreach` est `TargetTiles@+0x78`, cf. l'entete
    du module) -> le gate lit la tuile de la cible et l'effet est POSE sur l'entite-tuile, exactement
    comme les autres poses tile-domain du port (`AddEffect(Tiles(Target()))` d'`OnFireDamageAbility`).

    `source` = `Owner@+0x30` (le porteur du trait), et c'est LU : la surcharge appelee ici est celle a
    SIX parametres (`DSLBehaviors$$AddEffect(dsl, type, stateRef, source, targets, options)`), donc le
    selecteur SOURCE est EXPLICITE -- contrairement a la surcharge a CINQ parametres d'
    `OnFireDamageAbility`, dont le selecteur source NUL fait retomber
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` sur la cible (`source_from_target`).

    Duree : `options ZERO` -> AUCUN override -> `DefaultAmountOfRounds(0x5c4) = 2 rounds`, converti
    dans `AddEffectOperation` (la table du port porte deja cette entree). Rend l'id de tuile
    REELLEMENT despoilee, ou None (pas de board, tuile deja sous status-effect, re-pose no-op)."""
    board = getattr(state, "board", None)
    if target_id is None or board is None or state.effects is None:
        return None
    e = state.get_entity(int(target_id))
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is None:
        return None
    # `!HasTileStatusEffect(Current)` — MEME lecture que le trigger de POSE et que le gate du coup
    # (filtre `IsTileStatusEffect`, cf. `_target_tile_effects`).
    if _target_tile_effects(state, int(target_id)):
        return None
    tile_id = board.id_at(pc.col, pc.row)
    if tile_id is None:
        return None
    eff = _ops_effects.AddEffectOperation.execute(
        state, source=int(owner_id), target=int(tile_id),
        effect_type=int(EffectType.DespoiledGround),
        name=EffectType.DespoiledGround.name,
        duration_override=None)
    return int(tile_id) if eff is not None else None


class LetTheGalaxyBurnResetAbility(TriggeredAbility):
    """`LetTheGalaxyBurn_ResetAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour) — les DEUX volets :

        If( IsPersistentData(0x5ca, Owner, Get(<statique>)) & AttackUsedAttackDamage,
            Foreach( TargetTiles, If(!HasTileStatusEffect(Current), AddEffect(1476)) ) )
      + ClearPersistentData( 0x5ca, Owner, Get(<statique>) )                    # INCONDITIONNEL

    ORDRE : l'`op_Addition` evalue le `If` AVANT le `ClearPersistentData` -> le flag est LU d'abord,
    efface ensuite. Un port qui effacerait en tete rendrait le volet 2 mort a tous les coups.

    `Foreach(TargetTiles)` : cote port, `On(9)` part **PAR CIBLE** (mirror
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`, qui appelle `FinishAttack` apres chaque
    cible -- cf. `dispatch/attack.py::finish_attack_triggers`), donc l'ensemble a iterer ici est le
    singleton `{ev.target_id}` : le natif et le port posent le meme nombre d'effets, chacun sur la
    tuile de SA cible."""
    event_id = _ON_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return ev.actor_id == self.owner_id            # OwnerIsCaster (fin de SON attaque)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        c = _persistent(state, self.owner_id)
        if c is None:
            return None
        had = LET_THE_GALAXY_BURN_PERSISTENT_KEY in c.data
        # VOLET 2, AVANT le clear (ordre de l'`op_Addition`). `AttackUsedAttackDamage` =
        # `AbilityEntities+0xf9`, threade sur l'event (`byte` brut natif : non renseigne = 0 = FAUX).
        despoiled = (_despoil_target_tile(state, self.owner_id, ev.target_id)
                     if (had and bool(ev.attack_used_attack_damage)) else None)
        c.clear_persistent_data(LET_THE_GALAXY_BURN_PERSISTENT_KEY)
        return {"trait": "LetTheGalaxyBurn", "unit": int(self.owner_id), "cleared": bool(had),
                "despoiled_tile": despoiled}
