"""`ChampionOfTheFeastAbility` (`TriggeredAbilityType` 0x43e = 1086) -- le passif de
`templSwordBrother` << Sword Brother Godswyl >> : a la fin de son activation, il frappe UN ennemi
adjacent et lui reduit l'ARMURE pour le reste de la bataille (#419-r6-r2).

i2 (`Abilities/ChampionOfTheFeast_CurrentLevelDescription`) : « After moving, deals {nrOfHits}x
{minDmg}-{maxDmg} Power Damage to an adjacent enemy and reduces this enemy's Armour by
{armorReduction} Armour for the rest of the battle. If Sword Brother Godswyl does not move, then this
ability triggers at the end of his turn. »

>>> LE GAP. Ce passif n'etait dans AUCUN des quatre registres de trigger (`TRAIT_TRIGGERS`,
    `ABILITY_TRIGGERS`, `ACTIVE_ABILITY_TRIGGERS`, `EFFECT_TRIGGERS`) : offline, Godswyl terminait
    son activation SANS frapper et SANS poser le malus d'armure -- ni erreur, ni crash. Il etait
    invisible de `docs/rl/combat-ability-coverage.md`, qui n'audite que les `activeAbilities`.

==================================================================================================
CHAINE NATIVE (decompile = verite, build `rnca9r7q6c`)
==================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ChampionOfTheFeastAbility$$CreateTrigger` =

    On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive = <DSLTriggers+0x20>)
      & get_OwnerIsActor
      & op_LogicalNot( AmountIsZero( Damageable( AdjacentEnemies(Caster@DSLSelectors+0x48,
                                                                 unique = true,
                                                                 UnitSelectionType.OnlyAliveAndTargetable = 3) ) ) )

  * `On(0x1c)` = « l'unite a TERMINE son activation ». DEUX emetteurs natifs, tous deux gardes par
    le MEME flag `UnitFlag.ArrivedAtFinalTile` (donc AU PLUS UN fire par activation) :
    `IdunBattle.Operations.MoveUnitOperation$$Execute` (apres son 1er deplacement) et
    `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` (cloture du tour d'une unite qui n'a
    PAS bouge, `!forced`). C'est LITTERALEMENT le « After moving / if he does not move, at the end
    of his turn » de l'i2 -- les deux branches sont le MEME event.
    Vecteur porte : `arrived_at_final_tile_triggers` (`triggers/dispatch/move_death.py`), deja en
    place pour `ArcaneShield`, `SpiritualLeader` et `FabricatorClawArray`.
  * le volet « owner vivant » (`<DSLTriggers+0x20>`) est deja le gate `CanGetAbilityTrigger` du
    dispatch porte (`dispatch/core.evaluate_trigger_operation`) -- pas re-ecrit ici ;
  * `AmountIsZero(selector)` sous `op_LogicalNot` = « il existe au moins un ennemi adjacent
    damageable ». ⚠ Ce sous-arbre ne contient AUCUN `PickRandomly` -> le trigger consomme
    **ZERO tirage** (contraste `FabricatorClawArray`, dont le `GetTargetSelector` en porte un).

`...$$GetPossibleTargets` = `Damageable(AdjacentEnemies(...))` -- le MEME pool que le trigger.

`...$$GetTarget` = `Otherwise( PickRandomly(UnitsWithoutTrait(pool, 0x19 = UnitTrait.Immune, 3),
                                            1, allowDuplicates = 0, maxDuplicates = 0x7fffffff,
                                            ignoreForcedTargets = false),
                              PickRandomly(pool, 1, 0, 0x7fffffff, false) )

`...$$CreateBehaviour` =

    target = Cache( <GetTarget ci-dessus>, matchAbilityEntities = true )
    AttackWithAttackDamage( caster        = Owner@DSLSelectors+0x30,
                            target        = target,
                            amount        = BaseTriggeredAbility$$MinMaxDamage(abilityState),
                            damageProfile = Nullable(GetDamageProfileOrDefault(
                                                       DamageProfileType.Power = 0xe)),
                            hits          = BaseTriggeredAbility$$GetHits(),
                            abilityOrEffect = AbilityOrEffect(this),
                            options       = <default>,
                            selectionType = UnitSelectionType.OnlyTargetable = 2 )
    op_Addition
    IfAlive( target,
             AddStaticStatModifierEffect( targets    = target,
                                          effectType = 0x43b = 1083 ChampionOfTheFeast_ReduceArmor,
                                          statType   = 0x10  = 16 FixedArmor,
                                          amount     = DSLFormulas.Direct( -GetVariableForLevel(
                                                         config, 0x30 = armorReduction,
                                                         abilityState, fallbackToDefault = 0) ),
                                          turns      = NULL,
                                          isHidden   = false ) )

QUATRE points tranches AU DECOMPILE, pas au tooltip :

  1. LA PREFERENCE `UnitsWithoutTrait(Immune)` n'est PAS un filtre dur -- c'est un `Otherwise`.
     Le natif PREFERE un ennemi adjacent NON-`Immune`, et retombe sur le pool COMPLET si tous le
     sont. Ecrire un filtre sec priverait Godswyl de sa frappe face a un mur d'unites `Immune`.
     `0x19 = 25` est bien `UnitTrait.Immune` (`enums.tsv`, `IdunBattle.Entities.Enum.UnitTrait`),
     pas `Idun_Conceal` (24) ni `Imperial` (26).
  2. LE `Cache` EST FONCTIONNEL, pas une optimisation. Sans lui, l'arbre serait evalue DEUX fois
     (une pour l'attaque, une pour l'effet) -> DEUX tirages `PickRandomly` au lieu d'un, et
     potentiellement DEUX cibles differentes des que le pool depasse 1. Le port utilise le noeud
     `Cache` (memoisation observable, `entities/selectors/geometry.py`), rebati a CHAQUE fire.
  3. `IfAlive` est evalue APRES l'attaque : un ennemi que la frappe TUE ne recoit pas le malus
     d'armure. L'identite `IfAlive(sel, then) == If(IsAlive(sel), then)` est celle du natif
     (`DSLBehaviors$$IfAlive` appelle `DSLTriggers$$IsAlive` puis `DSLBehaviors$$If`).
  4. LE PROFIL est `Power` et vient de la CONFIG. `GetDamageProfileOrDefault(0xe)` lit
     `constants.damageProfile` du gameconfig avec `DamageProfileType.Power = 14` en DEFAUT ; la
     config de `ChampionOfTheFeast` porte litteralement `"damageProfile": "Power"` -> les deux
     concordent. `nrOfHits` = `"1"`, `attackRangeType` = `"Melee"`.

==================================================================================================
FORME DU PORT (doctrine #149)
==================================================================================================
L'artefact natif est un `CreateTrigger` + un `CreateBehaviour` : c'est donc un ARBRE DSL, et c'en
est un ici -- aucun ciblage n'est recable a la main. Tout le vocabulaire existait deja
(`Damageable`, `AdjacentEnemies`, `UnitsWithoutTrait`, `PickRandomly`, `Otherwise`, `Cache`,
`AttackWithAttackDamage`, `AddStaticStatModifierEffect`, `If`, `IsAlive`, `Seq`) : ce module ne
fait que le CABLER. La FRONTIERE reste le `.Execute` des feuilles.

EQUIVALENCE RNG DU `Otherwise` (prouvee, pas supposee -- meme demonstration que
`barbed_ovipositor.py`) : `IdunBattle.DSL.OtherwiseSelector$$Select` evalue la branche primaire,
teste `Enumerable.Any`, et n'evalue le repli QUE si elle est vide (LAZY) ; et
`PickRandomAmountSelector$$Select` sort AVANT tout tirage quand `candidates.Count < 1` (loi #130,
foyer `abilities/loki/splash.py::_pick_randomly_n`). Le port ecrit donc les DEUX `PickRandomly` du
natif tels quels : 1 tirage si le pool non-Immune est non vide, 1 tirage sinon (sur le pool
complet), 0 si les deux sont vides -- mais le trigger garantit deja que le pool complet ne l'est
pas, donc **exactement 1 tirage par fire**.

RESIDUS NOMMES :
  * `selectionType = UnitSelectionType.OnlyTargetable = 2` (dernier argument d'
    `AttackWithAttackDamage`) et `= 3 OnlyAliveAndTargetable` (sur `AdjacentEnemies` /
    `UnitsWithoutTrait`) : le port n'a pas ce parametre cote selecteurs sources -- residu deja
    partage par TOUS les call-sites d'`AdjacentEnemies`/`AdjacentFriends`, pas propre a ce port.
  * `matchAbilityEntities = true` du `Cache` : le port memoise par INSTANCE de noeud (slot unique),
    la variante dict-keyee par contexte n'est pas portee. Inerte ici -- l'arbre est rebati a chaque
    fire et n'est evalue que sous UN contexte top-level.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import Seq, If as BIf
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Count
from .....entities.selectors.geometry import Cache, Otherwise, PickRandomly
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import AdjacentEnemies, Damageable, UnitsWithoutTrait
from .....entities.stats import StatType
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsZero, IsAlive, Not, OwnerIsActor, TriggerAnd
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddStaticStatModifierEffect
from ....components import StatsComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "ChampionOfTheFeast"
ARMOR_REDUCTION_KEY = "armorReduction"       # `AbilityVariableType` 0x30 = 48
DAMAGE_PROFILE = "Power"                     # `GetDamageProfileOrDefault(DamageProfileType.Power = 0xe)`
# `UnitsWithoutTrait(pool, 0x19, 3)` -- la PREFERENCE (pas un filtre dur), cf. en-tete point 1.
TRAIT_PREFER_WITHOUT = UnitTrait.Immune      # 0x19 = 25
PICK_MAX_DUPLICATES = 0x7FFFFFFF             # `maxDuplicatesAllowed` des DEUX `PickRandomly`

_ON_ARRIVED = int(EventTriggerType.ArrivedAtFinalTile)      # 0x1c = 28


def champion_of_the_feast_possible_targets():
    """`...$$GetPossibleTargets` = `Damageable(AdjacentEnemies(Caster@DSLSelectors+0x48,
    unique = true, UnitSelectionType.OnlyAliveAndTargetable = 3))`.

    `AdjacentEnemies` = `Enemies(Units(AdjacentTiles(caster)) - {caster})` (anneau-1 hex, self
    exclu, filtre team != caster) ; `Damageable` = alive & hp > 0. Selecteur DSL PUR.

    Une NOUVELLE instance a chaque appel, EXPRES : le natif appelle cette fabrique depuis
    `CreateTrigger` **et** depuis `GetTarget`, et l'ordre du pool n'est PAS retrie (c'est lui qui
    decide QUI est piquee des que le pool depasse 1)."""
    return Damageable(AdjacentEnemies(Caster()))


def champion_of_the_feast_target():
    """`...$$GetTarget`, enveloppe du `Cache` de `...$$CreateBehaviour` :

        Cache( Otherwise( PickRandomly(UnitsWithoutTrait(pool, Immune), 1, 0, 0x7fffffff, false),
                          PickRandomly(pool,                            1, 0, 0x7fffffff, false) ),
               matchAbilityEntities = true )

    Les DEUX `PickRandomly` du natif sont ecrits tels quels (equivalence RNG demontree en en-tete).
    Le `Cache` est ce qui fait que l'attaque ET le `AddStaticStatModifierEffect` frappent la MEME
    unite avec UN SEUL tirage (en-tete point 2)."""
    prefer = PickRandomly(UnitsWithoutTrait(champion_of_the_feast_possible_targets(),
                                            TRAIT_PREFER_WITHOUT),
                          1, False, PICK_MAX_DUPLICATES, False)
    fallback = PickRandomly(champion_of_the_feast_possible_targets(),
                            1, False, PICK_MAX_DUPLICATES, False)
    # `...ChampionOfTheFeastAbility$$CreateBehaviour` pousse `matchAbilityEntities = 1` (mode
    # DICT), qui est le defaut du noeud.
    return Cache(Otherwise(prefer, fallback))


def champion_of_the_feast_trigger_tree():
    """`...$$CreateTrigger`, moins le volet `On(0x1c)` / owner-vivant que porte le DISPATCH :

        get_OwnerIsActor & op_LogicalNot( AmountIsZero( GetPossibleTargets() ) )

    `AmountIsZero` prend un SELECTEUR cote natif (surcharge `DSLTriggers$$AmountIsZero(selector)`,
    qui construit `NOT AmountIsGreater(selector, <Zero>)`) ; le noeud porte prend une VALEUR, d'ou
    le `Count(...)` explicite -- meme predicat, `count <= 0`. ZERO tirage (en-tete)."""
    return TriggerAnd(OwnerIsActor(),
                      Not(AmountIsZero(Count(champion_of_the_feast_possible_targets()))))


def armor_reduction(state: State, owner_id: int) -> int:
    """`AbilityConfiguration.GetVariableForLevel(config, 0x30 = armorReduction, abilityState,
    fallbackToDefault = 0)`.

    Resolu par l'APPELANT parce que le natif le resout lui aussi AVANT de batir l'arbre : il appelle
    `GetVariableForLevel` puis enveloppe la valeur dans `DSLFormulas$$Direct` -- c'est une CONSTANTE
    de l'arbre, pas un `ConfigVar` paresseux (meme forme que `fabricator_claw_array.hp_to_repair`).

    `armorReduction` figure dans le `variablesAffectedByRarityBonus` de la config -> le multiplier de
    rarete s'applique. `ChampionOfTheFeast` est un PASSIF -> slot `passive_ability_level`, JAMAIS
    `active_ability_level`. 0 si l'unite/son contexte/la variable manquent -> la feuille est un
    no-op."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    if ctx is None:
        return 0
    lvl = getattr(ctx, "passive_ability_level", None)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    return int(ability_var(ABILITY_ID, ARMOR_REDUCTION_KEY, lvl, multiplier_pct=mult) or 0)


def champion_of_the_feast_behaviour_tree(target, amount: int):
    """`...$$CreateBehaviour` = `AttackWithAttackDamage(...) op_Addition IfAlive(target, AddStatic...)`.

    `op_Addition` alloue la MEME `CombinedBehaviour` que `op_BitwiseAnd` -> noeud `Seq` (les deux
    branches sont des effets PURS, donc aucune ne court-circuite l'autre).

    `amount` est NEGATIF : c'est le `Direct( -GetVariableForLevel(0x30) )` du natif, ou la negation
    est appliquee A LA VALEUR avant d'entrer dans le noeud (cf. l'en-tete de
    `entities/effects/loki/champion_of_the_feast.py`, point 1).

    `duration_rounds`/`duration_turns` a `None` = pas d'override -> `DefaultAmountOfRounds` ne
    connait pas 0x43b -> effet PERMANENT (« for the rest of the battle »)."""
    attack = AttackWithAttackDamage(target, ABILITY_ID, DAMAGE_PROFILE,
                                    is_melee=True, multi=True, level_slot="passive")
    debuff = AddStaticStatModifierEffect(target, int(EffectType.ChampionOfTheFeast_ReduceArmor),
                                         int(StatType.FIXED_ARMOR), amount,
                                         name=EffectType.ChampionOfTheFeast_ReduceArmor.name)
    return Seq(attack, BIf(IsAlive(target), debuff))


class ChampionOfTheFeastAbility(TriggeredAbility):
    """`ChampionOfTheFeastAbility` (`TriggeredAbilityType` 0x43e = 1086, passif `templSwordBrother`)
    -- cf. l'en-tete du module pour la chaine native, la doctrine #149 et les residus.

    `On(0x1c = ArrivedAtFinalTile) & OwnerIsActor & NOT AmountIsZero(Damageable(AdjacentEnemies))`
    -> `AttackWithAttackDamage(<1 ennemi adjacent, non-Immune de preference>, nrOfHits x Power)
       + IfAlive(<la MEME cible>, AddStaticStatModifierEffect(1083, FixedArmor, -armorReduction,
                                                              PERMANENT))`."""
    event_id = _ON_ARRIVED
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.ChampionOfTheFeast)     # 0x43e = 1086

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` moins le volet porte par le dispatch (`On(0x1c)` + owner vivant).

        N'evalue AUCUN `PickRandomly` (le sous-arbre du trigger n'en porte pas) -> aucune
        consommation PRNG dans le gate, contrairement a `FabricatorClawArray`."""
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        return bool(champion_of_the_feast_trigger_tree().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        amount = armor_reduction(state, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        target = champion_of_the_feast_target()          # UNE instance -> UN `Cache` pour les 2 feuilles
        champion_of_the_feast_behaviour_tree(target, -amount).execute(entities, ectx)
        atk = next((p for (n, p) in ectx.emitted if n == "AttackWithAttackDamage"), None)
        debuff = next((p for (n, p) in ectx.emitted if n == "AddStaticStatModifierEffect"), None)
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "target": (atk.get("target") if atk else None),
                "attack": (atk.get("attack") if atk else None),
                "armor_reduction": (debuff.get("amount") if debuff else None),
                "dsl": True}
