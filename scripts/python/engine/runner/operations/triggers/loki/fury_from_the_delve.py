"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryFromTheDelveAbility` (`TriggeredAbilityType`
0x5f8 = 1528), passif de `votanBeserk` (Leagues of Votann, HERO `kind` lineup, HORS pool par defaut
-> injection catalogue). UN nom de kit, **DEUX classes portees** : le `CreateTrigger` natif est une
DISJONCTION `AbilityTrigger.op_BitwiseOr` de deux `On()`, et le `CreateBehaviour` se ventile sur son
parametre `triggerType` -- patron `LetTheGalaxyBurn` / `ThrillSeekers`.

## LES TROIS CORPS NATIFS, LUS VERBATIM SUR `rnca9r7q6c`

### `...FuryFromTheDelveAbility$$CreateTrigger` (`op_BitwiseOr` de deux conjonctions)

    ( On( 0x2a = PreUnitAbility, ownerNeedsToBeAlive: 1 )
        op_BitwiseAnd  IsNormalAttack
        op_BitwiseAnd  get_OwnerIsActor )
    op_BitwiseOr
    ( On( 0x26 = NormalAttack, ownerNeedsToBeAlive: 1 )
        op_BitwiseAnd  get_OwnerIsActor
        op_BitwiseAnd  IsAlive( <DSLSelectors+0x60 = Target> ) )

### `...FuryFromTheDelveAbility$$CreateBehaviour(abilityState, triggerType)`

    if (triggerType != 0x2a)   // donc le bras NormalAttack
        return DSLBehaviors.If(
            DSLFormulas.GetPersistentData( AbilityOrEffect(1528),
                                           <DSLSelectors+0x30 = Owner>,
                                           "TARGET_HEALTH_ABOVE_HALF" ),
            DSLBehaviors.AddEffect( 0x429 = 1065 Pinned,
                                    AbilityStateReference,
                                    source  = <DSLSelectors+0x30 = Owner>,
                                    targets = <DSLSelectors+0x60 = Target>,
                                    turns   = DSLFormulas.TurnsFromRounds(
                                                  GetNumberConstant(0x45 = nrOfRounds) ) ),
            DSLBehaviors.AttackWithAttackDamage(
                    caster = <DSLSelectors+0x30 = Owner>, target = <DSLSelectors+0x60 = Target>,
                    amount = BaseTriggeredAbility.MinMaxDamage(abilityState),
                    damageProfile = BaseTriggeredAbility.GetDamageProfile(),
                    hits = BaseTriggeredAbility.GetHits(),
                    abilityOrEffect = AbilityOrEffect(1528),
                    options = <struct ZEROEE>, selectionType = 2 ) );
    return GetCheckTargetHealthBehaviour();

### `...FuryFromTheDelveAbility$$GetCheckTargetHealthBehaviour` (le bras PreUnitAbility)

    DSLBehaviors.SetPersistentData(
        AbilityOrEffect(1528),
        unit  = <DSLSelectors+0x30 = Owner>,
        key   = DSLFormulas.Get("TARGET_HEALTH_ABOVE_HALF"),
        value = DSLTriggers.AmountIsGreater(
                    DSLFormulas.StatAmount( <DSLSelectors+0x60 = Target>,
                                            0x5 = StatType.Health, 0x0 = StatPart.Current,
                                            modificationEntity = null, selectionType = 0 ),
                    DSLFormulas.PercentageOf(
                        DSLFormulas.StatAmount( <DSLSelectors+0x60 = Target>,
                                                0x5 = StatType.Health, 0x2 = StatPart.Maximum,
                                                modificationEntity = null, selectionType = 0 ),
                        percentage   = GetNumberConstant(0x12 = hpPct),
                        roundingRule = 0 = RoundingRule.Default ) ) )

Lisible : **avant** chaque attaque NORMALE du porteur on MEMORISE << la cible etait-elle au-dessus
de `hpPct` % de ses PV max ? >> ; **apres** le coup on relit ce flag -- cible etait saine -> on la
`Pinned`, cible etait deja entamee -> on lui remet une attaque gratuite de `nrOfHits` coups.

Gameconfig `passiveAbilities.FuryFromTheDelve` (LU) : `nrOfRounds = 1`, `hpPct = 50`,
`nrOfHits = 2`, `damageProfile = Eviscerate`, `attackRangeType = Melee`, variables `minDmg`/`maxDmg`.
La cle native `"TARGET_HEALTH_ABOVE_HALF"` (literal `0x3386b48` de `metadata/string_literals.tsv`)
et `hpPct = 50` se confirment mutuellement.

## CINQ LECTURES QUI NE SE DEVINENT PAS

1. **`If` est la surcharge `formula`, pas la surcharge `trigger`** -- tranche par l'ADRESSE du
   `call` (`...FuryFromTheDelveAbility$$CreateBehaviour+0x2e1` -> `DSLBehaviors$$If` a `+0xea3360`,
   dont `frida/methods.tsv` donne `formula:IdunBattle.DSL.IAmountFormula`). Son corps enveloppe la
   formule dans **`DSLTriggers.AmountIsGreaterThanZero`** : le test est donc `> 0`, jamais `!= 0`.
   La surcharge `IAbilityTrigger` (`+0xea34c0`) est celle qu'appelle `ECogSupportAbility`, et la
   surcharge `ITargetsSelector` (`+0xea3410`) une troisieme -- les trois sont homonymes.
2. **`SetPersistentData` avec une VALEUR-TRIGGER ecrit 1 ou 0**, et c'est LU :
   `DSLBehaviors$$SetPersistentData` (`+0xea5d40`, surcharge `value:IAbilityTrigger`) fabrique
   `DSLFormulas.ConditionalAmount(trigger, <DSLFormulas+0x20>, <DSLFormulas+0x18>)`, et
   `IdunBattleLogic.Entities.DSLFormulas$$.ctor` pose `+0x18 = Direct(0)`, `+0x20 = Direct(1)`
   (`+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`). Le sac ne contient donc
   qu'un booleen 1/0, et le `> 0` du point 1 le relit exactement.
3. **Cle ABSENTE -> la formule rend 0 -> branche ELSE**, donc l'ATTAQUE. Corps de
   `IdunBattle.Entities.Triggers.GetPersistentDataFormula$$Calculate` : `TryGetPersistData` sur cle
   absente laisse son `out` a `default(T)`, et c'est cette valeur qui est rendue. Consequence
   directe : **ne porter que le bras `NormalAttack` ferait partir l'attaque supplementaire a TOUS
   les coups** -- le bras `PreUnitAbility` n'est pas cosmetique, c'est lui qui arme le refus.
4. **Il n'y a AUCUN `ClearPersistentData`** dans ce kit (contraste `LetTheGalaxyBurn_ResetAbility`).
   Le flag n'est jamais efface : il est REECRIT a chaque `PreUnitAbility` d'attaque normale. C'est
   sain parce que les deux bras sont montes sur la meme sequence (le natif emet `PreUnitAbility` en
   tete d'`ActiveAbilityOperation$$ExecuteInternal`, `NormalAttack` a la cloture) -- mais un port
   qui ajouterait un clear << par hygiene >> changerait le comportement du bras 3.
5. **`StatPart` discrimine les deux `StatAmount`** : `0 = Current` contre `2 = Maximum` -- meme
   selecteur, meme `StatType`, seul le 3e argument change. Les confondre rendrait la condition
   `PV > 50 % PV` toujours FAUSSE (`PV_courants > PV_courants / 2` est vrai, en fait -- donc
   toujours VRAIE, et l'attaque supplementaire ne partirait JAMAIS). Le port passe par
   `HealthComponent.get_stat_part`, seul foyer de cette ventilation (#572-r1).

⚠ Offsets `DSLSelectors` de ce build : `Owner` 0x30, `Caster` 0x48, `Target` 0x60,
`ActiveTarget` 0x68.
⚠ **`0x68` disait `Current` ici, et c'etait FAUX** (corrige par #964-r1). Aucun selecteur `Current`
n'existe, ni au natif ni au port. Le discriminant :
`IdunBattle.Entities.Selectors.ActiveTargetSelector$$Select` lit `AbilityEntities+0x20` (avec repli
sur `+0x10`) et `...PreviousActiveTargetSelector$$Select` lit `+0x28` -- et c'est exactement le
champ `+0x20` qu'`IdunBattle.Entities.Selectors.UnitsWithAnyValidTargetSelector$$Select` ECRIT
avant chaque evaluation de son selecteur d'ability. Les deux autres citations du depot
(`runner/abilities/admec.py`, `triggers/loki/synaptic_linchpin.py`) disaient deja `ActiveTarget`.

## FACE DECISION : ABSENTE, et c'est une MESURE

`search_symbols_by_name("FuryFromTheDelve")` rend **six** symboles : les trois corps ci-dessus et
trois `IdunBattle.View.AbilityConfigs.Loki.FuryFromTheDelveVisuals*` (couche VUE, hors logique).
**Aucun `*Playbook`, aucun `*NonOwnerPlaybook`** -- ce passif n'a pas de face DECISION native, il
n'y a donc rien a porter de ce cote et rien a inscrire dans `NON_OWNER_MOVE_PLAYBOOKS` /
`NON_OWNER_ATTACK_PLAYBOOKS`. Ce n'est pas un residu : c'est un resultat.

## CRITERE DE L'EMETTEUR : OUI pour les DEUX faces

* `On(0x2a = PreUnitAbility)` -> `dispatch/ability.py::pre_unit_ability_triggers`, emis par les
  DEUX voies d'operation depuis #120 (attaque normale ET cast), avec `ability_type` renseigne --
  c'est ce champ que lit le gate `IsNormalAttack`.
* `On(0x26 = NormalAttack)` -> `dispatch/attack.py`, emis par `ExecuteTriggerAbilities` en cloture
  d'attaque normale (le meme vecteur que consomme `SpecialIssueCombiMelta`).

## CE QUE CE PORT N'ETABLIT PAS

* `selectionType = 2` (`UnitSelectionType.OnlyTargetable`, 9e argument d'`AttackWithAttackDamage`)
  n'est materialise par aucun etage du port -- residu PARTAGE par tous ses call-sites, ni cree ni
  aggrave ici.
* `options` = struct ZEROEE au call-site (5 qwords a 0, lus a l'assembleur) : ni `isForceOverkill`,
  ni `forceCrit`, ni `skipHitsModifiers`. C'est le defaut de la feuille portee.
* Le gate `!HasFlag(unit, 6 = Dead)` d'`AddEffectBehaviour$$Execute` est porte par le noeud
  `AddEffect` / `AddEffectOperation` PARTAGE, pas ici.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.behaviours import If
from .....entities.damage_profile_type import DamageProfileType
from .....entities.effect_type import EffectType
from .....entities.formulas import PercentageOf, StatAmount
from .....entities.selectors.accessors import Owner, Target
from .....entities.stats import StatPart, StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsGreater, AmountIsGreaterThanZero
from .....dsl.effects import ExecutionContext
from ....abilities.attack_type import is_normal_attack
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....components import PersistentDataComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig de la passiveAbility porteuse.
FURY_FROM_THE_DELVE = "FuryFromTheDelve"
#: `AbilityOrEffect(0x5f8)` -- la moitie ABILITY de la cle composite du sac persistant.
FURY_FROM_THE_DELVE_ID = int(TriggeredAbilityType.FuryFromTheDelve)      # 0x5f8 = 1528
#: `DSLFormulas.Get(<literal 0x3386b48>)` -- le `dataKey`, LU dans `metadata/string_literals.tsv`.
_PERSISTENT_DATA_KEY = "TARGET_HEALTH_ABOVE_HALF"
#: Cle composite offline `(abilityOrEffect, dataKey)` -- mirror de
#: `(AbilityOrEffect$$GetPersistentDataId(...), key)` cote natif (cf. `PersistentDataComponent`).
FURY_PERSISTENT_KEY = (FURY_FROM_THE_DELVE_ID, _PERSISTENT_DATA_KEY)

PINNED = int(EffectType.Pinned)                                          # 0x429 = 1065

#: `On(0x2a = PreUnitAbility, ownerNeedsToBeAlive = 1)` -- bras 1 de l'`op_BitwiseOr`.
_ON_PRE_UNIT_ABILITY = int(EventTriggerType.PreUnitAbility)              # 0x2a = 42
#: `On(0x26 = NormalAttack, ownerNeedsToBeAlive = 1)` -- bras 2.
_ON_NORMAL_ATTACK = int(EventTriggerType.NormalAttack)                   # 0x26 = 38

#: `GetNumberConstant(0x12)` / `GetNumberConstant(0x45)` -- des CONSTANTES (`GetNumberConstant`),
#: jamais des variables de niveau : le natif ne passe pas par `GetVariableForLevel` ici.
_HP_PCT_KEY = AbilityConstantType.hpPct.name                             # 0x12 = 18
_ROUNDS_KEY = AbilityConstantType.nrOfRounds.name                        # 0x45 = 69
#: Volet ATTAQUE : `MinMaxDamage(abilityState)` / `GetDamageProfile()` / `GetHits()`.
_MIN_KEY = AbilityVariableType.minDmg.name                               # 0xc = 12
_MAX_KEY = AbilityVariableType.maxDmg.name                               # 0xd = 13
_HITS_KEY = AbilityConstantType.nrOfHits.name                            # 0x2f = 47
#: `config.GetDamageProfile()` du gameconfig de CE passif (`damageProfile = "Eviscerate"`), LU --
#: jamais deduit du nom de l'ability ni du profil d'arme du porteur.
PROFILE = DamageProfileType.Eviscerate.name
#: `attackRangeType = "Melee"` au gameconfig -> l'attaque supplementaire est MELEE.
_IS_MELEE = True


def _ability_constant(state: State, owner_id: int, key: str, default: int) -> int:
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(<AbilityConstantType>)`.

    Les deux constantes de ce kit vivent dans `constants` (pas dans `variables`) : elles ne sont
    donc PAS indexees par le niveau, et le natif ne passe pas par `TryGetVariableArrayForLevel`.
    On lit le gameconfig du passif, jamais un `variables[level]`."""
    import gameconfig as GC
    cfg = (GC.ability(FURY_FROM_THE_DELVE) or {}).get("constants") or {}
    raw = cfg.get(key)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _persistent(state: State, owner_id: int) -> Optional[PersistentDataComponent]:
    """Get-or-create le `PersistentDataComponent` du porteur (le natif l'a d'office sur l'entite)."""
    e = state.get_entity(owner_id)
    if e is None:
        return None
    c = e.get_component(PersistentDataComponent)
    if c is None:
        c = PersistentDataComponent()
        e.add_component(c)
    return c


def target_health_above_threshold_trigger(hp_pct: int):
    """`value` du `SetPersistentData` -- MIRROR 1:1 de la formule native :

        AmountIsGreater( StatAmount(Target, Health, StatPart.Current),
                         PercentageOf( StatAmount(Target, Health, StatPart.Maximum),
                                       percentage = hpPct, roundingRule = Default ) )

    ⚠ `PercentageOf` cote port prend `(pct, base)` la ou le natif prend `(amount, percentage)` :
    l'ordre des deux operandes est INVERSE par la signature du noeud porte, pas par une lecture.
    `mode = 0` = `RoundingRule.Default` -> `Fix64.Round` demi-vers-le-PAIR (surtout pas `// 100`).
    La comparaison est STRICTE (`AmountIsGreater`) : une cible pile a `hpPct` % rend FAUX, donc
    l'attaque supplementaire -- c'est ce que le nom `..._ABOVE_HALF` dit aussi."""
    current = StatAmount(Target(), int(StatType.HEALTH), int(StatPart.CURRENT))
    maximum = StatAmount(Target(), int(StatType.HEALTH), int(StatPart.MAXIMUM))
    return AmountIsGreater(current, PercentageOf(Const(int(hp_pct)), maximum, 0))


def fury_from_the_delve_pinned_tree(rounds: int):
    """Branche << then >> : `AddEffect(0x429 = Pinned, AbilityStateReference, source = Owner@+0x30,
    targets = Target@+0x60, turns = TurnsFromRounds(GetNumberConstant(nrOfRounds)))`.

    ⚠ La surcharge appelee est celle a SIX parametres (`effectType, abilityState, source, targets,
    turns`), donc le selecteur SOURCE est EXPLICITE et vaut `Owner` -- `source_from_target` reste
    FAUX. C'est le contraste exact avec `SpecialIssueCombiMelta_AddEffectAbility`, qui pose le MEME
    effet 1065 par la surcharge a CINQ parametres (selecteur source NUL -> la source EST la cible).
    Recopier ce voisin de forme aurait ecrit la mauvaise source."""
    return AddEffect(PINNED, EffectType.Pinned.name, Target(), duration_rounds=int(rounds))


def fury_from_the_delve_attack_tree():
    """Branche << else >> : `AttackWithAttackDamage(Owner, Target, MinMaxDamage, GetDamageProfile,
    GetHits, AbilityOrEffect(1528), options ZEROEE, selectionType = 2)`.

    `multi=False` : le natif passe `Target@+0x60` (le selecteur MONO-cible de l'evenement), pas une
    liste -- contraste `LegacyOfCombat`, dont la branche << else >> passe `AdjacentEnemies`.
    `level_slot="passive"` : `FuryFromTheDelve` est un PASSIF, sa config se resout au niveau des
    passives du porteur."""
    return AttackWithAttackDamage(Target(), FURY_FROM_THE_DELVE, PROFILE, is_melee=_IS_MELEE,
                                  min_key=_MIN_KEY, max_key=_MAX_KEY, hits_key=_HITS_KEY,
                                  level_slot="passive", ability_type=FURY_FROM_THE_DELVE_ID)


class FuryFromTheDelveCheckTargetHealthAbility(TriggeredAbility):
    """BRAS 1 de l'`op_BitwiseOr` -- `On(0x2a = PreUnitAbility) & IsNormalAttack & OwnerIsActor`
    -> `GetCheckTargetHealthBehaviour()` = `SetPersistentData(1528, Owner,
    "TARGET_HEALTH_ABOVE_HALF", <PV courants de la cible > hpPct % de son max>)`.

    C'est la face qui ARME le refus : sans elle la cle reste absente, `GetPersistentData` rend 0 et
    le bras 2 partirait TOUJOURS en attaque supplementaire (cf. l'en-tete, point 3)."""

    event_id = _ON_PRE_UNIT_ABILITY
    TRIGGERED_ABILITY_ID = TriggeredAbilityType.FuryFromTheDelve

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `IsNormalAttack` -- mirror `IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack` (#120),
        # lu sur `ev.ability_type`. Sans lui, le flag serait reecrit par n'importe quel CAST du
        # porteur, avec la cible de ce cast : un faux positif que le natif refuse.
        if not is_normal_attack(ev.ability_type):
            return False
        # `get_OwnerIsActor` = `AreEqual(Owner@+0x30, Actor@+0x40)`. Sur ce vecteur l'ACTEUR est le
        # caster de l'ability en cours (`ActiveAbilityOperation` construit son `AbilityEntities`
        # avec caster == actor).
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        # La formule lit `StatAmount(Target@+0x60, ...)` : sans cible resolvable il n'y a rien a
        # mesurer, et le natif n'ecrirait qu'un 0 sur un selecteur vide.
        if ev.target_id is None or state.get_entity(ev.target_id) is None:
            return False
        owner = state.get_entity(self.owner_id)
        uc = owner.get_component(UnitComponent) if owner is not None else None
        return uc is not None and bool(uc.alive)          # `On(..., ownerNeedsToBeAlive = 1)`

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        c = _persistent(state, self.owner_id)
        if c is None:
            return None
        hp_pct = _ability_constant(state, int(self.owner_id), _HP_PCT_KEY, 50)
        ents = entities_from_state(state, int(self.owner_id), ev.target_id, actor_id=ev.actor_id)
        above = bool(target_health_above_threshold_trigger(hp_pct).should_trigger(ents))
        # `ConditionalAmount(trigger, Direct(1), Direct(0))` -- le sac ne recoit QUE 1 ou 0
        # (en-tete, point 2). Ecrire un `bool` Python y passerait le controle `> 0` mais ne serait
        # plus le mirror de ce que le natif range.
        c.persist_data(FURY_PERSISTENT_KEY, 1 if above else 0)
        return {"passive": FURY_FROM_THE_DELVE, "unit": int(self.owner_id),
                "target": int(ev.target_id), "hp_pct": int(hp_pct),
                "target_health_above_half": above, "armed": True}


class FuryFromTheDelveAttackOrPinAbility(TriggeredAbility):
    """BRAS 2 de l'`op_BitwiseOr` -- `On(0x26 = NormalAttack) & OwnerIsActor & IsAlive(Target)`
    -> `If( GetPersistentData(...) > 0, AddEffect(Pinned, nrOfRounds), AttackWithAttackDamage(...) )`.

    Cible qui etait SAINE avant le coup -> `Pinned` ; cible deja entamee -> `nrOfHits` coups
    `Eviscerate` gratuits."""

    event_id = _ON_NORMAL_ATTACK
    TRIGGERED_ABILITY_ID = TriggeredAbilityType.FuryFromTheDelve

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):   # get_OwnerIsActor
            return False
        # `IsAlive(Target@+0x60)` -- gate EXPLICITE de ce bras (le bras 1 ne l'a pas). Une cible
        # abattue par le coup qui vient de porter ne recoit ni `Pinned` ni attaque supplementaire.
        tgt = state.get_entity(ev.target_id) if ev.target_id is not None else None
        if tgt is None:
            return False
        tuc = tgt.get_component(UnitComponent)
        if tuc is None or not tuc.alive:
            return False
        owner = state.get_entity(self.owner_id)
        uc = owner.get_component(UnitComponent) if owner is not None else None
        return uc is not None and bool(uc.alive)          # `On(..., ownerNeedsToBeAlive = 1)`

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        c = _persistent(state, self.owner_id)
        # `GetPersistentDataFormula$$Calculate` sur cle ABSENTE rend `default(T)` = 0 -> branche
        # ELSE. Le port reproduit exactement cette polarite (pas de `None` special-case).
        stored = 0 if c is None else int(c.try_get_persist_data(FURY_PERSISTENT_KEY) or 0)
        # `DSLBehaviors.If(formula, ...)` = `AmountIsGreaterThanZero(formula)` (en-tete, point 1).
        above = stored > 0
        rounds = _ability_constant(state, int(self.owner_id), _ROUNDS_KEY, 1)
        ents = entities_from_state(state, int(self.owner_id), ev.target_id, actor_id=ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `DSLBehaviors.If(formula, ...)` fabrique lui-meme
        # `DSLTriggers.AmountIsGreaterThanZero(<la formule>)` (en-tete, point 1) : le port ECRIT ce
        # noeud, il ne le collapse pas en un `bool`. La formule, elle, est deja evaluee -- le sac
        # persistant est un COMPOSANT ECS, pas une entree du `ctx` DSL, donc `GetPersistentData`
        # n'a pas de mirror-noeud a interposer ici.
        tree = If(AmountIsGreaterThanZero(Const(stored)),
                  fury_from_the_delve_pinned_tree(rounds),
                  fury_from_the_delve_attack_tree())
        tree.execute(ents, ectx)
        pinned = [p for (n, p) in ectx.emitted if n == "AddEffect"]
        atks = [p for (n, p) in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"passive": FURY_FROM_THE_DELVE, "unit": int(self.owner_id),
                "target": int(ev.target_id), "target_health_above_half": above,
                "pinned": bool(pinned and pinned[0].get("placed")),
                "rounds": int(rounds) if above else None,
                "attack": (atks[0].get("attack") if atks else None),
                "total": sum(int(p.get("total") or 0) for p in atks) if atks else None,
                "dsl": True}
