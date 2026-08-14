"""`Abilities.Triggered.Loki.APowerUpAbility` + les CINQ sous-classes de BOOST DE STAT (#1083-r1).

LES POWER-UPS SONT DES UNITES `Steppable` POSEES SUR LE PLATEAU : on marche dessus, elles MEURENT, et
c'est LEUR MORT qui donne le bonus a celui qui les a ecrasees. Le vecteur est donc exactement celui de
`HaywireMineSteppableAbility` (`loki/haywire_mine.py`) -- `On(1 = PreUnitDeath)` publie par
`IdunBattle.Operations.KillUnitOperation$$Execute` sous `KillUnitOperationOptions$$ForSteppable`,
avec `RecordDeathReason(..., DamageReason.Steppable)` grave AVANT.

--------------------------------------------------------------------------------------------------
ARTEFACTS NATIFS (decompile ghidra, build `rnca9r7q6c` -- decompile = verite)
--------------------------------------------------------------------------------------------------

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.APowerUpAbility$$CreateTrigger`, noeud par noeud
(`DSLFactory+0x78` = DSLBehaviors, `+0x80` = DSLFormulas, `+0x88` = DSLTriggers, `+0x90` =
DSLSelectors ; `DSLSelectors+0x30` = `Owner`, `+0x40` = `Actor`, `+0x48` = `Caster`, `+0x60` =
`Target` -- mapping MESURE sur `DSLTriggers$$get_OwnerIsActor` / `$$get_OwnerIsTarget` /
`$$get_OwnerIsCaster` / `$$get_CasterIsTarget`, qui construisent chacun le meme noeud a deux
selecteurs) :

    EventTrigger(1 = PreUnitDeath)
  & <DSLTriggers+0x70>                             # conjoint NEUTRE, cf. RESIDU 1 ci-dessous
  & NOT TargetIsOverkilled()
  & <DSLTriggers+0x70>                             # le MEME champ, lu une seconde fois
  & get_OwnerIsTarget                              # le POWER-UP est l'unite qui meurt (@0x178)
  & HasDeathReason(Owner@sel+0x30, 2 = DamageReason.Steppable, <Nullable VIDE>)
  & NOT HasTrait(Actor@sel+0x40, 0x1b = UnitTrait.Steppable)
  & IsAlive(Actor@sel+0x40)

C'est le trigger d'`HaywireMineSteppable` MOINS son `AreEnemies(Owner, Actor)` PLUS le gate overkill :
**un power-up profite a QUI QUE CE SOIT** qui marche dessus, ami comme ennemi. L'absence d'`AreEnemies`
est LUE (aucun appel a `DSLTriggers$$AreEnemies` dans le corps), pas deduite.

`...$$CreateBehaviour(abilityState, triggerType)` -- `target` = `Actor@sel+0x40` PARTOUT :

    AddShield(Actor)
  & AddPctBasedBoost(Actor)
  & AddAbsoluteBoost(Actor)
  & <SelfContainedBoostEffect>                     # Nothing() pour les CINQ, cf. RESIDU 2
  & AdditionalBehavior(Actor, abilityState)        # Nothing() sauf PowerUp_Armor

`...$$AddShield(target)` -- COMMUN aux 20 `PowerUp_*` :

    if (!TryGetNumberConstant(config, 0x50 = shieldPct, out pct))  return Nothing();
    pctF     = Direct(pct)
    duration = TurnsFromRounds( ConfigConst(0x45 = nrOfRounds, config) )
    amount   = PercentageOf( StatAmount(target, 5 = Health, 3 = Initial, null, 1 = OnlyAlive),
                             pctF, 0 = RoundingRule.Default )
    return If( AmountIsGreaterThanZero(pctF),
               CreateShield(target, amount, AbilityOrEffect(this), duration, null, stackable = 1),
               null )

`...$$AddPctBasedBoost(target)` -- `get_PctBasedStatBoost` = vslot `+0x378` :

    boost = this.PctBasedStatBoost;   if (boost == null) return Nothing();
    stat  = boost.<+0x10>            # StatType
    eff   = boost.<+0x14>            # EffectType
    key   = (stat != 5) ? 0x3b = dmgPct : 0x4f = healthPct
    pct   = GetNumberConstant(config, key)
    a = Nothing(); b = Nothing();
    if (stat == 5 /* Health */) {
        cached = Cache( PercentageOf( Cache(StatAmount(target, 5, 3 = Initial, null, 1)),
                                      Get(pct), 0 ) )
        b = ChangeStat(target, Stat(5,0,0), 2 = ChangeStatMode.Add, cached, null,
                       1 = OnlyAlive, isModifiable = 0, isHidden = 0)
        a = SetCache(cached)
    }
    mod = AddStaticStatModifierEffect(target, eff, stat, Get(pct), turns = null, isHidden = 0)
    return (a & mod) & b

`...$$AddAbsoluteBoost(target)` -- `get_AbsoluteStatBoost` = vslot `+0x388` :

    boost = this.AbsoluteStatBoost;   if (boost == null) return Nothing();
    amount = GetNumberConstant(config, boost.<+0x10> /* AbilityConstantType */)
    return AddStaticStatModifierEffect(target, boost.<+0x18> /* EffectType */,
                                       boost.<+0x14> /* StatType */, Get(amount),
                                       turns = null, isHidden = 0)

LES DEUX RECORDS, ET LEURS CHAMPS (types LUS dans `PctBasedStatBoostType$$PrintMembers` /
`AbsoluteStatBoostType$$PrintMembers`, qui `Enum.ToString` chaque champ contre son type) :

    record PctBasedStatBoostType (StatType @+0x10, EffectType @+0x14)
    record AbsoluteStatBoostType (AbilityConstantType @+0x10, StatType @+0x14, EffectType @+0x18)

LES CINQ SOUS-CLASSES, litteraux LUS a leur ctor :

| passif             | vslot surcharge         | valeurs                                                        |
|--------------------|-------------------------|----------------------------------------------------------------|
| `PowerUp_Damage`   | `get_PctBasedStatBoost` | `(StatType.Attack 0, EffectType.PowerUp_Damage 0x473)`           |
| `PowerUp_Health`   | `get_PctBasedStatBoost` | `(StatType.Health 5, EffectType.PowerUp_Health 0x477)`           |
| `PowerUp_Hits`     | `get_AbsoluteStatBoost` | `(extraHit 0x2b, StatType.ExtraHits 0x11, PowerUp_Hits 0x475)`   |
| `PowerUp_MeleeHits`| `get_AbsoluteStatBoost` | `(extraHit 0x2b, ExtraHitsMelee 0x17, PowerUp_MeleeHits 0x476)`  |
| `PowerUp_Armor`    | **`AdditionalBehavior`**| `AddDynamicStatModifierEffect(target, PowerUp_Armor 0x472,`      |
|                    |   (vslot `+0x398`)      | `StatType.FixedArmor 0x10, turns = null, isHidden = 0)`          |

⚠ `PowerUp_Armor` N'EST PAS un boost de stat au sens des quatre autres : il ne surcharge NI
`get_PctBasedStatBoost` NI `get_AbsoluteStatBoost`, mais `AdditionalBehavior` -- et il pose un
modificateur **DYNAMIQUE** dont la magnitude est recalculee par
`IdunBattle.Entities.Effects.PowerUp_ArmorEffect$$GetDynamicStatModificationAmount` (portee dans
`engine/entities/effects/loki/power_up.py`). Il RESTE dans le lot (meme `CreateBehaviour`, meme
trigger, meme montage), mais par un TROISIEME vslot. Mesure, pas suppose.

⚠ LES ORDINAUX DES DEUX ENUMS DIVERGENT, ET SILENCIEUSEMENT :
`TriggeredAbilityType.PowerUp_MeleeHits` = 1138 = `EffectType.PowerUp_Armor` ;
`TriggeredAbilityType.PowerUp_Hits` = 1140 = `EffectType.StormboyzStrike_TeleportingIn`.
Seul `PowerUp_Damage` (1139) coincide, par accident. D'ou le membre NOMME partout ci-dessous.

CONFIG (gameconfig, build `rnca9r7q6c`, ZERO hardcode -- toutes lues par `ability_var`) :

    PowerUp_Armor     : healthPct=100  nrOfRounds=1  shieldPct=100
    PowerUp_Damage    : dmgPct=100     nrOfRounds=1  shieldPct=100
    PowerUp_Health    : healthPct=200  nrOfRounds=1  shieldPct=100
    PowerUp_Hits      : extraHit=2     nrOfRounds=1  shieldPct=100
    PowerUp_MeleeHits : extraHit=4     nrOfRounds=1  shieldPct=100

Le `healthPct` de `PowerUp_Armor` n'est PAS lu par `AddPctBasedBoost` (l'ability n'a pas de
`PctBasedStatBoost`) : c'est `PowerUp_ArmorEffect$$GetDynamicStatModificationAmount` qui le lit.

PORTEURS (gameconfig, section objets) -- une unite par passif, toutes du meme profil
`traits: [Steppable, Invincible, Immune]`, `activeAbilities: []` :
`powupArmor` / `powupDamage` / `powupHealth` / `powupHits` / `powupMeleeHits`.
AUCUNE n'est placee par le runner depuis un board (le canal `PowerUpUnits` n'est lu qu'au BUILD DE LA
BC par `BattleConfigBuilder$$GetBoostsConfig`, cf. `docs/rl/case-1083-powerup-le-board-ne-confronte-rien.md`) :
le montage de confrontation est `catalog_inject --units powup<X>` + `rl_duel build --seed-bc ...
--explicit-stats powup<X> --a-units "powup<X>,..."`.

DOCTRINE #149 : le TRIGGER est collapse imperativement (lecture d'etat pure -- meme choix que
`haywire_mine.py`, dont il est le jumeau) ; le BEHAVIOUR est un ARBRE DSL (`op_and` / `If` /
`CreateShield` / `AddStaticStatModifierEffect` / `AddDynamicStatModifierEffect` / `ChangeStat`).

RESIDUS NOMMES :
  1. `<DSLTriggers+0x70>` (lu DEUX fois dans la conjonction) n'est PAS porte. Il est construit dans
     `DSLTriggers$$.ctor` par `new <T>()` SANS argument, ou `<T>` est le MEME type que `+0x40` et que
     le `+0x48 = !new <T>()` voisin -- donc `<T>` est le trigger CONSTANT, `+0x40`/`+0x70` sa forme
     VRAIE et `+0x48` sa negation. Deux mesures independantes le confirment : (a)
     `DSLTriggers$$InitializeShared` compose `+0x30 = EventTrigger(0x21) & <+0x70> & OwnerIsActor` et
     `+0x38 = EventTrigger(0x41) & <+0x70> & OwnerIsActor` -- si `<+0x70>` etait FAUX ces deux
     triggers partages seraient morts ; (b) `BaseEffect$$NeedsRefreshing` fait un `isinst <T>` sur le
     trigger d'un effet pour decider qu'il n'a PAS besoin d'etre rafraichi. Conjoint neutre pour `&`,
     donc omis -- et c'est le SEUL noeud du trigger que ce port n'ecrit pas.
  2. `SelfContainedBoostEffect` (vslot `+0x368`, `Nullable<EffectType>`) : AUCUNE des 22 classes
     `PowerUp_*` ne le surcharge (balayage exhaustif de `data/symbols/rnca9r7q6c/ghidra/functions.tsv`
     -- un override rendant un `Nullable` NON VIDE aurait un corps non trivial, donc un proprietaire
     dans la table). La base rend `null`, la branche prise est `Nothing()`, et le volet est omis.
  3. `SetCache(cached)` / `Cache(...)` du volet HEALTH : le port n'a pas de memoisation de FORMULE.
     C'est INERTE ici, et c'est mesurable : la formule cachee lit `StatPart.Initial`, qu'aucun des
     deux volets qu'elle alimente n'ecrit (`AddStaticStatModifierEffect` ecrit la part MODIFICATION,
     `ChangeStat(Health, Add)` la part COURANTE). Les deux lectures rendent donc la meme valeur, dans
     l'ordre natif comme dans l'ordre porte.
  4. `Nothing()` (kind E) n'existe pas cote port : les volets absents sont OMIS de la conjonction.
     `Seq` etant associatif et `Nothing` neutre, l'arbre porte est le meme.
  5. Les arguments `selectionType = 1 (OnlyAlive)`, `isModifiable = 0`, `isHidden = 0`, `stackable = 1`
     n'ont pas d'equivalent dans les feuilles portees -- meme residu que les autres call-sites.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.behaviours import If as IfBehaviour, op_and
from .....entities.damage_reason import DamageReason
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Get, PercentageOf, StatAmount, TurnsFromRounds
from .....entities.selectors.accessors import Actor
from .....entities.stats import StatPart, StatType
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsGreaterThanZero
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import (AddDynamicStatModifierEffect,
                                              AddStaticStatModifierEffect, CreateShield)
from ....abilities.behaviours.stats import ChangeStat
from ....components import UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, _unit_trait_names
from .reactivate_overwatch import has_death_reason

#: `TryGetNumberConstant(config, 0x50)` / `ConfigConst(0x45, config)` d'`APowerUpAbility$$AddShield`.
SHIELD_PCT_KEY = AbilityConstantType.shieldPct          # 0x50 = 80
SHIELD_ROUNDS_KEY = AbilityConstantType.nrOfRounds      # 0x45 = 69
#: `key = (stat != 5) ? 0x3b : 0x4f` d'`APowerUpAbility$$AddPctBasedBoost` -- le CHOIX est en dur dans
#: le natif, il ne vient pas du record.
PCT_KEY_HEALTH = AbilityConstantType.healthPct          # 0x4f = 79
PCT_KEY_OTHER = AbilityConstantType.dmgPct              # 0x3b = 59
#: `NOT HasTrait(Actor@sel+0x40, 0x1b)` -- un power-up ecrase par un AUTRE power-up ne donne rien.
STEPPABLE_TRAIT = UnitTrait.Steppable                   # 0x1b = 27


def _const(ability_name: str, key) -> "int | None":
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config, <key>)` -- collapse
    scalaire du noeud `ConfigConst`/`Get`, meme choix que `haywire_mine.py::_config` : le noeud porte
    `ConfigConst` resout sa cle contre `ctx.config`, que le vecteur d'un trigger ne threade pas.
    `None` = cle ABSENTE, ce que le natif distingue explicitement pour `shieldPct` (`TryGetNumberConstant`
    rend `false` -> `Nothing()`)."""
    v = ability_var(ability_name, key.name, is_constant=True)
    return None if v is None else int(v)


def add_shield_tree(ability_name: str, turns: "int | None"):
    """`APowerUpAbility$$AddShield(target)` -- MIRROR 1:1, `target` = `Actor@sel+0x40`.

    `turns` = `TurnsFromRounds(ConfigConst(nrOfRounds))` DEJA evalue par l'appelant (la feuille portee
    `CreateShield` prend un scalaire en `duration`, cf. sa docstring) ; `None` quand la constante
    manque. Rend `None` quand `shieldPct` est absente -- c'est le `Nothing()` natif."""
    pct = _const(ability_name, SHIELD_PCT_KEY)
    if pct is None:
        return None                                  # `!TryGetNumberConstant(...)` -> `Nothing()`
    # `PercentageOf(StatAmount(target, Health, Initial, ...), Direct(pct), Default)` -- l'ordre des
    # deux operandes est INVERSE cote port (`PercentageOf(pct, base, mode)`), cf. `entities/formulas.py`.
    amount = PercentageOf(Const(pct),
                          StatAmount(Actor(), int(StatType.HEALTH), int(StatPart.INITIAL)))
    shield = CreateShield(Actor(), amount, duration=turns)
    # `If( AmountIsGreaterThanZero(Direct(pct)), <shield>, null )` : le gate porte sur le POURCENTAGE
    # (une constante), pas sur le montant -- un `shieldPct = 0` explicite rend donc `Nothing()`.
    return IfBehaviour(AmountIsGreaterThanZero(Const(pct)), shield)


def add_pct_based_boost_tree(ability_name: str, stat_type: int, effect_type: int):
    """`APowerUpAbility$$AddPctBasedBoost(target)` -- MIRROR 1:1. `None` si le record est `null`
    (l'appelant ne le construit alors pas)."""
    key = PCT_KEY_HEALTH if int(stat_type) == int(StatType.HEALTH) else PCT_KEY_OTHER
    pct = _const(ability_name, key)
    if pct is None:
        return None
    name = EffectType(int(effect_type)).name
    mod = AddStaticStatModifierEffect(Actor(), int(effect_type), int(stat_type), Get(pct), name=name)
    if int(stat_type) != int(StatType.HEALTH):
        return mod                                   # `(Nothing & mod) & Nothing` == `mod`
    # Volet HEALTH : le stat-mod monte la HP **MAXIMALE**, le `ChangeStat(Add)` remplit d'autant la HP
    # COURANTE -- sans lui, un +200 % de PV max laisserait l'unite au meme nombre de PV.
    cached = PercentageOf(Const(pct),
                          StatAmount(Actor(), int(StatType.HEALTH), int(StatPart.INITIAL)))
    change = ChangeStat(Actor(), int(StatType.HEALTH), "add",
                        source=f"powerup:{name}",
                        amount=lambda entities, ectx, _n=cached: int(_n.evaluate(entities)))
    return op_and(mod, change)                       # `(SetCache & mod) & change`, cf. RESIDU 3


def add_absolute_boost_tree(ability_name: str, const_key, stat_type: int, effect_type: int):
    """`APowerUpAbility$$AddAbsoluteBoost(target)` -- MIRROR 1:1. `None` si le record est `null` ou si
    la constante manque."""
    amount = _const(ability_name, const_key)
    if amount is None:
        return None
    return AddStaticStatModifierEffect(Actor(), int(effect_type), int(stat_type), Get(amount),
                                       name=EffectType(int(effect_type)).name)


class APowerUpAbility(TriggeredAbility):
    """La BASE des 22 `PowerUp_*` : elle porte le trigger et le `CreateBehaviour` en entier, les
    sous-classes ne fournissant que leurs trois vslots (`get_PctBasedStatBoost` `+0x378`,
    `get_AbsoluteStatBoost` `+0x388`, `AdditionalBehavior` `+0x398`).

    `fire_on_death = True` : l'owner EST le mourant (`get_OwnerIsTarget`), donc `alive == False`
    quand le vecteur `On(1)` part -- meme regime qu'`HaywireMineSteppableAbility`."""

    event_id = int(EventTriggerType.PreUnitDeath)              # `EventTrigger(1)`
    fire_on_death = True

    #: Le NOM gameconfig de la `passiveAbilities` (= la cle du registre `ABILITY_TRIGGERS`).
    ABILITY_NAME: str = ""
    #: `get_PctBasedStatBoost` -> `(StatType, EffectType)` ou `None` (la base rend `null`).
    PCT_BASED_STAT_BOOST: "tuple | None" = None
    #: `get_AbsoluteStatBoost` -> `(AbilityConstantType, StatType, EffectType)` ou `None`.
    ABSOLUTE_STAT_BOOST: "tuple | None" = None

    def additional_behavior(self, state: State):
        """`AdditionalBehavior(target, abilityState)` (vslot `+0x398`) -- la base rend `null`, ce que
        `APowerUpAbility$$AddAdditionalBehavior` convertit en `Nothing()`."""
        return None

    # ── `APowerUpAbility$$CreateTrigger` (collapse imperatif, doctrine #149) ────────────────────────
    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `NOT TargetIsOverkilled()`. INERTE dans le regime du crush (`_kill_steppable_kill_unit`
        # passe `overkill=False`, mirror de `ForSteppable+0x46 = 0` qui interdit le flag `Overkilled`),
        # mais PORTE : c'est le seul noeud qui separe ce trigger de celui d'`HaywireMineSteppable`.
        if ev.overkill:
            return False
        # `get_OwnerIsTarget` : le POWER-UP est l'unite qui meurt (`AbilityEntities@0x178`).
        dying = ev.dying_id if ev.dying_id is not None else ev.target_id
        if dying is None or int(dying) != int(self.owner_id):
            return False
        # `HasDeathReason(Owner@sel+0x30, 2, <Nullable VIDE>)` -- canal `UnitComponent.death_source`,
        # grave par `KillUnitOperation$$RecordDeathReason` AVANT `On(1)`. Un `Nullable` VIDE = aucun
        # filtre d'`AbilityOrEffect`.
        if not has_death_reason(state, int(self.owner_id), int(DamageReason.Steppable), None):
            return False
        actor = ev.actor_id if ev.actor_id is not None else ev.killer_id
        if actor is None or int(actor) == int(self.owner_id):
            return False
        ae = state.get_entity(int(actor))
        if ae is None:
            return False
        # `NOT HasTrait(Actor@sel+0x40, Steppable)`.
        if has_trait(_unit_trait_names(state, int(actor)), STEPPABLE_TRAIT):
            return False
        # `IsAlive(Actor@sel+0x40)`.
        auc = ae.get_component(UnitComponent)
        return auc is not None and bool(auc.alive)
        # PAS d'`AreEnemies` : un power-up profite AUSSI a un allie (lu au decompile, cf. l'en-tete).

    # ── `APowerUpAbility$$CreateBehaviour` (arbre DSL) ──────────────────────────────────────────────
    def behaviour_tree(self, state: State, entities):
        """L'arbre COMPLET, dans l'ordre natif :
        `AddShield & AddPctBasedBoost & AddAbsoluteBoost & <SelfContained> & <Additional>`."""
        rounds = _const(self.ABILITY_NAME, SHIELD_ROUNDS_KEY)
        # `TurnsFromRounds(ConfigConst(nrOfRounds))` -- evalue ICI parce que la feuille `CreateShield`
        # prend sa duree en scalaire (`ShieldComponent.add_or_update_shield(remaining=...)`).
        turns = (None if rounds is None
                 else int(TurnsFromRounds(Const(int(rounds))).evaluate(entities)))
        volets = [add_shield_tree(self.ABILITY_NAME, turns)]
        if self.PCT_BASED_STAT_BOOST is not None:
            stat, eff = self.PCT_BASED_STAT_BOOST
            volets.append(add_pct_based_boost_tree(self.ABILITY_NAME, int(stat), int(eff)))
        if self.ABSOLUTE_STAT_BOOST is not None:
            const_key, stat, eff = self.ABSOLUTE_STAT_BOOST
            volets.append(add_absolute_boost_tree(self.ABILITY_NAME, const_key, int(stat), int(eff)))
        volets.append(self.additional_behavior(state))
        volets = [v for v in volets if v is not None]        # cf. RESIDU 4 (`Nothing()` non porte)
        if not volets:
            return None
        arbre = volets[0]
        for v in volets[1:]:
            arbre = op_and(arbre, v)
        return arbre

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        actor = ev.actor_id if ev.actor_id is not None else ev.killer_id
        if actor is None:
            return None
        # `AbilityEntities` du vecteur `On(1)` : owner == caster == le POWER-UP (`Owner@sel+0x30`),
        # target == le mourant == le power-up (`get_OwnerIsTarget`), actor == celui qui a marche
        # dessus (`Actor@sel+0x40`, cible de TOUT le behaviour).
        entities = entities_from_state(state, int(self.owner_id), int(self.owner_id),
                                       actor_id=int(actor))
        arbre = self.behaviour_tree(state, entities)
        if arbre is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        arbre.execute(entities, ectx)
        emis = {n: p for n, p in ectx.emitted}
        return {"passive": self.ABILITY_NAME, "power_up": int(self.owner_id),
                "stepper": int(actor),
                "shield": (emis.get("CreateShield") or {}).get("amount"),
                "stat_mod": (emis.get("AddStaticStatModifierEffect")
                             or emis.get("AddDynamicStatModifierEffect")),
                "heal": (emis.get("ChangeStat") or {}).get("amount"),
                "dsl": True}


class PowerUpDamageAbility(APowerUpAbility):
    """`PowerUp_DamageAbility$$get_PctBasedStatBoost` = `new PctBasedStatBoostType(0, 0x473)` --
    `StatType.Attack` / `EffectType.PowerUp_Damage`, donc constante `dmgPct` (stat != Health)."""
    ABILITY_NAME = "PowerUp_Damage"
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.PowerUp_Damage)         # 1139
    PCT_BASED_STAT_BOOST = (StatType.ATTACK, EffectType.PowerUp_Damage)


class PowerUpHealthAbility(APowerUpAbility):
    """`PowerUp_HealthAbility$$get_PctBasedStatBoost` = `new PctBasedStatBoostType(5, 0x477)` --
    `StatType.Health` / `EffectType.PowerUp_Health`, donc constante `healthPct` ET le volet
    `ChangeStat(Health, Add, cached)` qui remplit les PV COURANTS."""
    ABILITY_NAME = "PowerUp_Health"
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.PowerUp_Health)         # 1137
    PCT_BASED_STAT_BOOST = (StatType.HEALTH, EffectType.PowerUp_Health)


class PowerUpHitsAbility(APowerUpAbility):
    """`PowerUp_HitsAbility$$get_AbsoluteStatBoost` = `new AbsoluteStatBoostType(0x2b, 0x11, 0x475)`
    -- `AbilityConstantType.extraHit` / `StatType.ExtraHits` / `EffectType.PowerUp_Hits`."""
    ABILITY_NAME = "PowerUp_Hits"
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.PowerUp_Hits)           # 1140
    ABSOLUTE_STAT_BOOST = (AbilityConstantType.extraHit, StatType.EXTRA_HITS,
                           EffectType.PowerUp_Hits)


class PowerUpMeleeHitsAbility(APowerUpAbility):
    """`PowerUp_MeleeHitsAbility$$get_AbsoluteStatBoost` = `new AbsoluteStatBoostType(0x2b, 0x17,
    0x476)` -- `extraHit` / `StatType.ExtraHitsMelee` / `EffectType.PowerUp_MeleeHits`."""
    ABILITY_NAME = "PowerUp_MeleeHits"
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.PowerUp_MeleeHits)      # 1138
    ABSOLUTE_STAT_BOOST = (AbilityConstantType.extraHit, StatType.EXTRA_HITS_MELEE,
                           EffectType.PowerUp_MeleeHits)


class PowerUpArmorAbility(APowerUpAbility):
    """`PowerUp_ArmorAbility$$AdditionalBehavior(target, abilityState)` -- LE SEUL des cinq a passer
    par ce vslot, corps ENTIER :

        return AddDynamicStatModifierEffect(target, 0x472 = EffectType.PowerUp_Armor,
                                            0x10 = StatType.FixedArmor, turns = null,
                                            isHidden = 0);

    L'overload a cinq arguments (`targets, effectType, statType, turns, isHidden`) ne prend PAS de
    selecteur SOURCE : `AddStatModifierEffectBehaviour$$Execute` retombe donc sur LA CIBLE, d'ou
    `source_sel = Actor()` cote port. La MAGNITUDE vit dans la classe d'effet
    (`engine/entities/effects/loki/power_up.py::PowerUpArmorEffect`), comme le natif la tient dans
    `PowerUp_ArmorEffect$$GetDynamicStatModificationAmount`."""
    ABILITY_NAME = "PowerUp_Armor"
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.PowerUp_Armor)          # 1136

    def additional_behavior(self, state: State):
        return AddDynamicStatModifierEffect(Actor(), Actor(), int(EffectType.PowerUp_Armor),
                                            int(StatType.FIXED_ARMOR),
                                            name=EffectType.PowerUp_Armor.name)


#: Les CINQ entrees de `ABILITY_TRIGGERS` de cette tranche -- cle = le NOM gameconfig de la passive.
POWER_UP_STAT_BOOST_ABILITIES = {
    PowerUpArmorAbility.ABILITY_NAME: PowerUpArmorAbility,
    PowerUpDamageAbility.ABILITY_NAME: PowerUpDamageAbility,
    PowerUpHealthAbility.ABILITY_NAME: PowerUpHealthAbility,
    PowerUpHitsAbility.ABILITY_NAME: PowerUpHitsAbility,
    PowerUpMeleeHitsAbility.ABILITY_NAME: PowerUpMeleeHitsAbility,
}
