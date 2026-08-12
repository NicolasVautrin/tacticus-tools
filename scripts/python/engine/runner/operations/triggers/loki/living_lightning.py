"""`LivingLightning` (`TriggeredAbilityType` 0x3ef = 1007) -- le passif de `necroPlasmancer`
<< Thutmose >> (Necrons, HERO), sa triggered-ability DERIVEE `LivingLightning_MoveEffect`
(0x3fc = 1020) et le retrait de l'effet 1020.

C'est le DERNIER item manquant du kit de Thutmose (son active `HarbingerOfDestruction` 1008 est
portee et validee).

i2 : « After moving, deals 1x {minDmg}-{maxDmg} Direct Damage to one random adjacent enemy. If
Thutmose does not move, then this ability triggers at the end of his turn. »
⚠ Le tooltip DIT << adjacent >> et le decompile dit AUTRE CHOSE : le rayon est
`If(<il existe un ennemi adjacent>, 1, constants.range = 2)` -- s'il n'y a AUCUN ennemi adjacent,
l'eclair part quand meme, sur un ennemi du disque de rayon 2. Recopier l'i2 aurait rendu l'ability
muette dans exactement le regime ou elle est la plus visible.

⚠ NAMESPACE : les deux classes vivent sous `IdunBattleLogic.Entities.Abilities.**Active**.Loki.`
mais leur BASE, LUE dans `data/symbols/<build>/frida/classes.tsv`, est
`IdunBattle.Entities.Abilities.BaseTriggeredAbility` -- ce sont des PASSIFS (meme piege que
`RelentlessMarchAbility`). Elles entrent donc dans `ABILITY_TRIGGERS`, PAS dans
`handler.ABILITY_CLASSES` : ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne s'appliquent
(`probe_181` / `probe_120` portent sur `ABILITY_CLASSES`, aucune entree ajoutee).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`). Toutes les surcharges sont tranchees par l'ADRESSE du
`call` (`probe_951_call_targets.py`), jamais a l'oeil.
================================================================================================

## 1. `...LivingLightningAbility$$GetPossibleTargets(targetAmount)`

    radius = DSLFormulas.If(
                 DSLTriggers.AmountIsGreaterThanZero(                      # surcharge SELECTEUR
                     DSLSelectors.AdjacentEnemies(Caster@DSLSelectors+0x48, unique: 1, sel: 3)),
                 <DSLFormulas+0x20> = Direct(1),
                 DSLFormulas.Get(AbilityConfiguration.GetNumberConstant(0x16 = range)) )

    return DSLSelectors.SurroundingTiles(CasterTile@+0x50, includeCenter: 0, radius, onlyMovable: 0)
           |> DSLSelectors.UnobscuredTiles(fromAnyTiles: CasterTile@+0x50, _)
           |> DSLSelectors.Units(_, unique: 1, selectionType: 3)
           |> DSLSelectors.Enemies(of: Caster@+0x48, _, selectionType: 3)
           |> DSLSelectors.Damageable(_)
           |> DSLSelectors.PickRandomly(_, amount: targetAmount, allowDuplicates: 0,
                                        maxDuplicatesAllowed: 0x7fffffff, ignoreForcedTargets: 0)

`<DSLFormulas+0x20>` = `Direct(1)` : etabli par `IdunBattleLogic.Entities.DSLFormulas$$.ctor`
(`+0x18 = Direct(0)`, `+0x20 = Direct(1)`, `+0x28 = Direct(2)`), deja LU par plusieurs ports.
C'est aussi le `targetAmount` que les deux appelants passent -> **UNE seule cible**.

`$$GetEnemiesInRange(targetAmount, range)` est le MEME corps avec le rayon en parametre : c'est le
helper C# qu'`GetPossibleTargets` inline. Il n'a AUCUNE xref CODE (seulement les entrees de la table
de methodes) -- il n'existe donc pas de second chemin de ciblage.

`Damageable(entities)` = `UnitsWithoutTrait(entities, 0x40e = UnitTrait.Invincible, 3)` (LU).

## 2. `...LivingLightningAbility$$CreateTrigger`

    DSLTriggers.On(EventTriggerType.ArrivedAtFinalTile = 0x1c, ownerNeedsToBeAlive: true)
      & DSLTriggers.get_OwnerIsActor
      & op_LogicalNot( DSLTriggers.AmountIsZero( GetPossibleTargets(<DSLFormulas+0x20> = Direct(1)) ) )

`On(0x1c)` porte les DEUX moities de l'i2 : le vecteur porte (`dispatch/move_death.py::
arrived_at_final_tile_triggers`) a DEUX emetteurs natifs, `MoveUnitOperation$$Execute` (apres un
deplacement) et la cloture de tour d'une unite qui n'a PAS bouge -- tous deux gardes par le MEME
flag `UnitFlag.ArrivedAtFinalTile`. C'est exactement le << if Thutmose does not move >> du tooltip,
et il n'y a donc rien a ajouter cote port.

## 3. `...LivingLightningAbility$$CreateBehaviour(abilityState, triggerType)`

    DSLBehaviors.AttackWithAttackDamage(
        caster        = Caster@DSLSelectors+0x48,
        target        = GetPossibleTargets(<DSLFormulas+0x20> = Direct(1)),
        amount        = BaseTriggeredAbility.MinMaxDamage(abilityState)
                        = DSLFormulas.RandomAmount( GetVariableForLevel(0xc = minDmg),
                                                    GetVariableForLevel(0xd = maxDmg) ),
        damageProfile = DSLSelectors.DamageProfileFromConfig(config)   # constants.damageProfile
        hits          = DSLFormulas.Direct( GetNumberConstant(0x2f = nrOfHits) ),
        abilityOrEffect = AbilityOrEffect( <this+0x10> = TriggeredAbilityType 1007 ),
        options       = Nullable<AttackDamageBehaviourOptions> VIDE,
        selectionType = UnitSelectionType.OnlyTargetable = 2 )

`<this+0x10>` est lu par un getter au corps `mov eax,[rcx+0x10] ; ret` que ghidra nomme
`CenterSpace.Free.MersenneTwister$$get_Count` -- corps DEDUPLIQUE par IL2CPP, le nom est celui d'un
proprietaire ARBITRAIRE. La signature de `AbilityOrEffect$$op_Implicit` qui le consomme
(`triggeredAbility : IdunBattle.Entities.Enum.TriggeredAbilityType`) tranche : c'est le type de
l'ability elle-meme.

## 4. `...LivingLightningMoveEffectAbility` (1020) -- le MARQUEUR de deplacement

    $$CreateTrigger =
        DSLTriggers.On(EventTriggerType.PreUnitMove = 0x1f, ownerNeedsToBeAlive: true)
          & DSLTriggers.get_OwnerIsActor
          & DSLTriggers.AmountIsEqualOrGreater(                          # surcharge SELECTEUR
                DSLSelectors.Enemies( of: Owner@DSLSelectors+0x30,
                                      DSLSelectors.Units(
                                          DSLSelectors.AdjacentTiles(TargetTiles@+0x78),
                                          unique: 1, sel: 3),
                                      sel: 3 ),
                DSLFormulas.Direct(1) )

    $$CreateBehaviour =
        DSLBehaviors.AddEffect( 0x3fc = EffectType.LivingLightning_MoveEffect,
                                AbilityStateReference, targets = Owner@+0x30,
                                turns = Nullable<int> VIDE )

`$$TargetTilesHasAdjacentEnemies` est le helper C# INLINE dans `CreateTrigger` (corps identique a
sa queue, aucune xref CODE).

`TargetTiles@+0x78` sur le vecteur pre-move = la DESTINATION : `MoveUnitOperation$$
EvaluatePreMoveTriggers` passe la MEME liste `position` en `casterTiles` ET en `targetTiles`
(lecture deja etablie par `hateful_assault.py`). Cote port : `TriggerEvent.dest_tile`.

    IdunBattle.Entities.Effects.Loki.LivingLightning_MovingEffect$$CreateRemoveEffectTrigger =
        DSLTriggers.On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive: true) & get_OwnerIsActor

## 5. MONTAGE -- une DERIVEE de TRIGGERED, pas d'ACTIVE

1020 est monte par `StaticBattleRules.**TriggeredAbility**$$GetDerivedTriggeredAbilities`
(`<statics>+0x88`), dont le `.cctor` ne peuple QUE DEUX entrees -- `0x3ef -> [0x3fc]` (1007
LivingLightning -> 1020 LivingLightning_MoveEffect) et `0x48e -> [0x491]` (1166 TheWrathfulDead ->
1169 TheWrathfulDead_Overkill). C'est un dict DISTINCT de
`StaticBattleRules.**ActiveAbility**$$GetDerivedTriggeredAbilities` (`<statics>+0x30`), que mirroire
`ACTIVE_ABILITY_TRIGGERS` et qui est indexe par `ActiveAbilityType`.

Cote port, les deux chemins convergent sur la MEME cle -- le nom gameconfig `LivingLightning` de
`units.passiveAbilities` : ecrire les deux classes sous `ABILITY_TRIGGERS["LivingLightning"]` monte
donc EXACTEMENT l'ensemble que le natif monte. Le registre `ACTIVE_ABILITY_TRIGGERS` serait, lui,
le mauvais : sa cle est une ability ACTIVE, et l'active de `necroPlasmancer` est
`HarbingerOfDestruction`.

## 6. FORME DU PORT (doctrine #149)

Les deux `CreateBehaviour` sont des ARBRES DSL (feuilles `AttackWithAttackDamage` / `AddEffect`),
batis de noeuds EXISTANTS -- `AdjacentEnemies`, `SurroundingTiles`, `UnobscuredTiles` (materialise
par cette tranche, cf. plus bas), `Units`, `Enemies`, `Damageable`, `If`/`AmountIsGreaterThanZero`.
Les `CreateTrigger` sont COLLAPSES imperativement dans `matches`.

`UnobscuredTiles` n'existait PAS comme noeud (residu `#287-r11-r2-r1-r3`), et le motif du blocage
etait litteralement << les deux `LivingLightning` ne sont pas portes, donc aucun SECOND consommateur
ne peut justifier le noeud seul >>. Cette tranche EST ce second consommateur : le noeud est
materialise dans `entities/selectors/tiles.py` et consomme ici. Le rebranchement de la DECISION de
`mv71.py` sur ce noeud reste ouvert (foyer d'un autre residu).

## 7. RESIDUS NOMMES

  * **DECALAGE RNG du gate de trigger, NON CONFRONTE.** Le natif evalue
    `AmountIsZero(GetPossibleTargets(...))` DANS le trigger, donc il traverse `PickRandomly`, dont
    le `PickRandomAmountSelector$$Select` TIRE. Le port evalue le POOL (sans `PickRandomly`) :
    VALEUR identique (`PickRandomly(pool, 1)` est vide ssi `pool` l'est), mais un tirage MT
    potentiellement en moins. Le fold `pick_n=1` du behaviour, lui, consomme exactement comme le
    natif (`_pick_randomly_n`, confronte live bit-exact #130/#215). Si un ecart de degat apparait
    live A CIBLE IDENTIQUE, c'est ce decalage qu'il faut regarder EN PREMIER.
  * `selectionType = 2` (`OnlyTargetable`) du 8e argument d'`AttackWithAttackDamage` : le port ne le
    thread pas (le noeud n'expose pas ce parametre) -- foyer partage, hors tranche.
  * `maxDuplicatesAllowed = 0x7fffffff` / `allowDuplicates = 0` de `PickRandomly` : sans effet a
    `amount = 1`.
  * `Damageable` cote port filtre `alive & hp > 0` la ou le natif fait
    `UnitsWithoutTrait(Invincible, sel: 3)` : ecart PREEXISTANT du noeud partage, pas introduit ici
    (aucun porteur d'`Invincible` dans un roster de duel).
  * L'effet 1020 n'a AUCUN lecteur cote port : son unique consommateur natif est
    `IdunBattle.View.AbilityConfigs.Loki.LivingLightningVisuals`. Il est pose et retire pour que
    l'etat d'effets du port suive celui du natif, sans consequence de jeu.
  * `IdunBattle.AI.Playbook.*` : aucun playbook natif ne porte le nom `LivingLightning`
    (recensement par la colonne << classe declarante >> de `frida/methods.tsv`) -- il n'y a donc pas
    de face DECISION a porter, contrairement a `TimesplinterMantle`.
"""
from __future__ import annotations

from typing import Optional

import gameconfig as GC

from .....dsl.base import Const, TargetsSelector
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.formulas import If as IfAmount
from .....entities.selectors.accessors import CasterTile
from .....entities.selectors.tiles import Caster, UnobscuredTiles
from .....entities.selectors.accessors import SurroundingTiles
from .....entities.selectors.units import AdjacentEnemies, Damageable, Enemies, Units
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsGreaterThanZero
from .....entities.unit_selection_type import UnitSelectionType
from ....components import OwnerComponent, UnitComponent
from ....state import State
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, RemoveEffect
from ..base import EffectTrigger, TriggeredAbility, TriggerEvent, _unit_tile

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig de la passiveAbility porteuse (elle porte
#: aussi les variables `minDmg`/`maxDmg` et les constantes `range`/`nrOfHits`/`damageProfile`).
LIVING_LIGHTNING = "LivingLightning"
LIVING_LIGHTNING_ID = int(TriggeredAbilityType.LivingLightning)                 # 0x3ef = 1007
#: `AddEffect(effectType = 0x3fc, ...)` -- un `EffectType`. L'ordinal 1020 est aussi un
#: `TriggeredAbilityType` (celui de l'ability DERIVEE qui le pose) : la qualification n'est pas
#: decorative, les deux enums se croisent ici.
LIVING_LIGHTNING_MOVE_EFFECT = int(EffectType.LivingLightning_MoveEffect)       # 0x3fc = 1020
LIVING_LIGHTNING_MOVE_EFFECT_NAME = EffectType(LIVING_LIGHTNING_MOVE_EFFECT).name
LIVING_LIGHTNING_MOVE_ABILITY = int(TriggeredAbilityType.LivingLightning_MoveEffect)   # 1020

_SEL_ALIVE_TARGETABLE = int(UnitSelectionType.OnlyAliveAndTargetable)          # 3
#: `<DSLFormulas+0x20>` = `Direct(1)` (`IdunBattleLogic.Entities.DSLFormulas$$.ctor`).
_ONE = 1


def _ability_constant(key: str):
    """`AbilityConfiguration$$GetNumberConstant(<AbilityConstantType>)` /
    `DSLSelectors$$DamageProfileFromConfig(config)` : la CONSTANTE de l'ability, lue BRUTE dans le
    gameconfig (`constants.range` = 0x16, `constants.nrOfHits` = 0x2f,
    `constants.damageProfile` = 0x2e). LEVE si la cle manque -- un repli silencieux rendrait tout ce
    qui suit aveugle (meme convention que `runner/abilities/darkangels.py::_ability_profile`)."""
    consts = ((GC.ability(LIVING_LIGHTNING) or {}).get("constants") or {})
    if key not in consts:
        raise KeyError(f"{LIVING_LIGHTNING}: constante '{key}' absente du gameconfig")
    return consts[key]


def living_lightning_pool() -> TargetsSelector:
    """`...LivingLightningAbility$$GetPossibleTargets` PRIVE de son `PickRandomly` final -- l'arbre de
    CANDIDATS, MIRROR 1:1 du reste (cf. §1 de l'en-tete) :

        SurroundingTiles(CasterTile@0x50, includeCenter: 0,
                         If(AmountIsGreaterThanZero(AdjacentEnemies(Caster@0x48, 1, 3)),
                            Direct(1), Get(constants.range)))
        |> UnobscuredTiles(fromAnyTiles: CasterTile@0x50, _)
        |> Units(_, unique: 1, sel: 3)
        |> Enemies(of: Caster@0x48, _, sel: 3)
        |> Damageable(_)

    Le `PickRandomly` est FOLDE dans la feuille d'attaque (`pick_n=1`), qui est le seul endroit ou
    le port sait reproduire sa consommation de MT a l'identique.

    `Caster()` et `CasterTile()` : sur un triggered, `entities_from_state(state, owner_id, ...)`
    pose `caster == owner`, et le natif lit ici `Caster@+0x48` / `CasterTile@+0x50` -- deux slots
    DISTINCTS d'`Owner@+0x30`, mais qui coincident sur ce vecteur (`MoveUnitOperation` publie la
    meme unite en owner/actor/caster/target)."""
    caster, caster_tile = Caster(), CasterTile()
    radius = IfAmount(AmountIsGreaterThanZero(AdjacentEnemies(caster, Const(1),
                                                              selection_type=_SEL_ALIVE_TARGETABLE)),
                      Const(_ONE),                                  # <DSLFormulas+0x20> = Direct(1)
                      Const(int(_ability_constant("range"))))       # Get(GetNumberConstant(0x16))
    tiles = SurroundingTiles(caster_tile, radius, include_center=False)
    tiles = UnobscuredTiles(caster_tile, tiles)
    units = Units(tiles, selection_type=_SEL_ALIVE_TARGETABLE)
    return Damageable(Enemies(units, selection_type=_SEL_ALIVE_TARGETABLE))


def living_lightning_attack_tree() -> AttackWithAttackDamage:
    """`...LivingLightningAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. §3 de l'en-tete).

    `pick_n=1` = le FOLD du `PickRandomly(pool, Direct(1), ...)` natif qui ENVELOPPE le selecteur de
    cibles ; `multi=True` = le behaviour resout une LISTE (le natif fait `OrderBy` puis attaque
    chaque element) -- a `amount = 1` la liste a au plus un element, mais la FORME reste celle du
    natif et la consommation MT du tirage est exacte (`_pick_randomly_n`).

    `is_melee=False` : `attackRangeType = "Ranged"` au gameconfig, et le profil `DirectDamage` est
    lu dans `constants.damageProfile` (le natif fait `DamageProfileFromConfig(config)`), jamais
    devine du nom de l'ability.
    `level_slot="passive"` : `LivingLightning` est un PASSIF -> `minDmg`/`maxDmg` s'indexent au
    niveau de PASSIVE ability, pas a celui de l'active.
    Les coups viennent de `constants.nrOfHits` par le defaut `hits_key="nrOfHits"` du noeud = le
    `GetNumberConstant(0x2f)` natif."""
    return AttackWithAttackDamage(living_lightning_pool(), LIVING_LIGHTNING,
                                  str(_ability_constant("damageProfile")),
                                  is_melee=False, multi=True, pick_n=_ONE,
                                  level_slot="passive")


class LivingLightningAttackAbility(TriggeredAbility):
    """`LivingLightningAbility` (1007, passif de `necroPlasmancer` << Thutmose >>).

    A la FIN de l'activation de Thutmose -- apres son deplacement, OU a la cloture de son tour s'il
    n'a pas bouge (les deux emetteurs de `On(0x1c)`) -- il foudroie UN ennemi tire au hasard : parmi
    les adjacents s'il y en a, sinon dans le disque de rayon `constants.range` = 2, en ligne de vue.
    Cf. l'en-tete du module."""
    event_id = int(EventTriggerType.ArrivedAtFinalTile)          # On(0x1c = 28)
    TRIGGERED_ABILITY_ID = LIVING_LIGHTNING_ID                   # 0x3ef = 1007

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """COLLAPSE du `CreateTrigger` (§2). Le volet << owner vivant >> est deja le gate
        `CanGetAbilityTrigger` du dispatch ; restent `get_OwnerIsActor` et le gate d'existence de
        cible.

        ⚠ Le gate est evalue sur le POOL, pas sur `PickRandomly(pool, 1)` : meme VALEUR, un tirage
        MT de moins (residu nomme, §7)."""
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False                                         # get_OwnerIsActor
        entities = entities_from_state(state, self.owner_id, None)
        # `op_LogicalNot(AmountIsZero(<cibles>))` = « il existe au moins un candidat ».
        return bool(living_lightning_pool().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, None)
        living_lightning_attack_tree().execute(entities, ectx)
        atks = [p for (n, p) in ectx.emitted if n == "AttackWithAttackDamage"]
        if not atks:
            return None
        return {"passive": LIVING_LIGHTNING, "caster": int(self.owner_id),
                "attacks": [p.get("attack") for p in atks], "dsl": True}


class LivingLightningMoveEffectAbility(TriggeredAbility):
    """`LivingLightningMoveEffectAbility` (1020) -- la triggered-ability DERIVEE de 1007
    (`StaticBattleRules.TriggeredAbility$$GetDerivedTriggeredAbilities[0x3ef] = [0x3fc]`, §5).

    Quand Thutmose s'apprete a bouger vers une tuile qui a AU MOINS UN ennemi adjacent, elle pose
    sur lui le marqueur 1020, que `LivingLightning_MovingEffect` retire des l'arrivee. Le marqueur
    n'a AUCUN lecteur logique (son unique consommateur natif est la couche VISUELS) : il est porte
    pour que l'etat d'effets du port suive celui du natif."""
    event_id = int(EventTriggerType.PreUnitMove)                 # On(0x1f = 31)
    TRIGGERED_ABILITY_ID = LIVING_LIGHTNING_MOVE_ABILITY         # 0x3fc = 1020

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """COLLAPSE du `CreateTrigger` (§4) : `get_OwnerIsActor` puis
        `AmountIsEqualOrGreater(Enemies(Owner, Units(AdjacentTiles(TargetTiles@0x78), 1, 3), 3),
        Direct(1))`.

        `TargetTiles@+0x78` = la DESTINATION du pas (`EvaluatePreMoveTriggers` met la meme liste en
        `casterTiles` et `targetTiles`), threadee par `MoveUnitOperation.execute` dans
        `ev.dest_tile`. `dest_tile` absent (construction directe hors runner) -> le terme n'est pas
        evaluable : on le laisse PASSER et on le DIT, plutot que de bloquer un vecteur que le natif
        laisserait passer (meme convention que `hateful_assault.py`)."""
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False                                         # get_OwnerIsActor
        if ev.dest_tile is None:
            return True
        board = state.board
        owner = state.get_entity(self.owner_id)
        ooc = owner.get_component(OwnerComponent) if owner is not None else None
        if board is None or ooc is None:
            return True
        dest = (int(ev.dest_tile[0]), int(ev.dest_tile[1]))
        dest_id = board.id_at(dest[0], dest[1])
        if dest_id is None:
            return False
        ring = set(board.neighbours(dest_id))                    # AdjacentTiles(TargetTiles@0x78)
        for eid, e in state.entities.items():
            if int(eid) == int(self.owner_id):
                continue
            uc = e.get_component(UnitComponent)
            eoc = e.get_component(OwnerComponent)
            if uc is None or eoc is None or not uc.alive:        # `Units(..., sel: 3)` volet VIVANT
                continue
            if eoc.team == ooc.team:                             # `Enemies(of: Owner@+0x30, ...)`
                continue
            t = _unit_tile(state, board, int(eid))
            if t is not None and t in ring:
                return True                                      # `... >= Direct(1)`
        return False

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`AddEffect(0x3fc, AbilityStateReference, targets = Owner@+0x30, turns = Nullable VIDE)`.

        La surcharge retenue est celle a 4 parametres, SANS selecteur `source` -- elle passe
        litteralement `0` en `param_5` d'`AddEffectBehaviour..ctor`, et `AddEffectBehaviour$$Execute`
        retombe alors sur la CIBLE (`source_from_target=True`). Ici la cible EST l'Owner, donc les
        deux lectures coincident ; on ecrit quand meme la surcharge LUE.
        `duration_rounds=None` = le `Nullable<int>` VIDE ; `1020` est absent de
        `DefaultAmountOfRounds` -> effet PERMANENT, retire par `LivingLightningMovingRemoveOnArrived`."""
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, None)
        AddEffect(LIVING_LIGHTNING_MOVE_EFFECT, LIVING_LIGHTNING_MOVE_EFFECT_NAME, Caster(),
                  duration_rounds=None, source_from_target=True).execute(entities, ectx)
        placed = [p for (n, p) in ectx.emitted if n == "AddEffect"]
        if not placed:
            return None
        return {"passive": LIVING_LIGHTNING, "owner": int(self.owner_id),
                "effect": LIVING_LIGHTNING_MOVE_EFFECT,
                "placed": bool(placed[0].get("placed"))}


class LivingLightningMovingRemoveOnArrived(EffectTrigger):
    """`IdunBattle.Entities.Effects.Loki.LivingLightning_MovingEffect$$CreateRemoveEffectTrigger` =
    `On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive: true) & get_OwnerIsActor` ->
    `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<cette instance>)`.

    Sans cette entree le marqueur 1020 serait PERMANENT (aucune duree posee, absent de
    `DefaultAmountOfRounds`) : divergence d'etat silencieuse.

    COLLAPSE ASSUME, identique a `ChronometronExtraDamageRemove` : le natif retire L'INSTANCE, le
    port retire tous les stacks non consommes du type sur le porteur."""
    effect_type = LIVING_LIGHTNING_MOVE_EFFECT                   # 0x3fc = 1020
    event_id = int(EventTriggerType.ArrivedAtFinalTile)          # 0x1c = 28

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)  # get_OwnerIsActor

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(LIVING_LIGHTNING_MOVE_EFFECT, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": LIVING_LIGHTNING_MOVE_EFFECT_NAME, "owner": int(self.owner_id),
                "removed": removed}
