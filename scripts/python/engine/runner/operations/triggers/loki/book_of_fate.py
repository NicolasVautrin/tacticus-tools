"""`BookOfFate` -- relique `R_Booster_Crit_BookOfFate`, `TriggeredAbilityType` 0x5b5 = 1461.
TROIS porteurs autorises (`items/R_Booster_Crit_BookOfFate/allowedUnits`, LU) : `blackPossession`
<< Volk Ravensoul >> (Black Legion), `thousInfernalMaster` et `thousSorcerer` (Thousand Sons).
Tous `kind = lineup`. #1008.

i2 (`Abilities/BookOfFate_CurrentLevelDescription`) : << After the relic bearer performs a normal
attack, a friendly adjacent Summon performs a normal attack against an enemy in range, if possible.
If the summon is a Daemon, it deals +{[extraDmg]} Damage with this attack. >>

===================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- UNE classe native, DEUX arbres
===================================================================================================

Slots lus : `DSLSelectors+0x30 Owner`, `+0x68 ActiveTarget`. `<ctx>+0x78 DSLBehaviors`,
`+0x80 DSLFormulas`, `+0x88 DSLTriggers`, `+0x90 DSLSelectors`.

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BookOfFateAbility$$CreateTrigger`

    On( 0x26 = EventTriggerType.NormalAttack, ownerNeedsToBeAlive = 1 )
  & get_OwnerIsCaster
  & IsAlive( Owner@+0x30 )
  & AmountIsGreaterThanZero(
        UnitsWithTrait( AdjacentFriends( Owner@+0x30, unique = true,
                                         UnitSelectionType.OnlyAliveAndTargetable = 3 ),
                        UnitTrait.Summon = 2, OnlyAliveAndTargetable ) )

Le dernier conjoint est un `AmountIsGreaterThanZero(ITargetsSelector)` (surcharge SELECTEUR, pas
formule) : il n'exige QUE la presence d'un summon ami adjacent -- **pas** qu'il ait une cible. Le
filtre << in range >> de l'i2 vit dans le BEHAVIOUR (`UnitsWithAnyValidTarget`), pas ici.

## `...BookOfFateAbility$$CreateBehaviour(entities, abilityState, triggerType)`

    extraDmg   = GetVariableForLevel( config@this+0x20, AbilityVariableType.extraDmg = 8,
                                      abilityState, 0 )
    affectedId = ConfigConstString( triggeredAbilityConfigId@this+0x10,
                                    AbilityConstantType.affectedUnitId = 0x8c )
                 # gameconfig : constants.affectedUnitId = "thousSmnDaemonPrince"

    adj  = UnitsWithTrait( AdjacentFriends( Owner@+0x30, true, 3 ), Summon, 3 )
    pool = UnitsWithAnyValidTarget( adj )          # surcharge a UN argument -> HasAnyValidTargetSelector

    A = UnitsWithId(      pool, affectedId,     3 )    # le Daemon Prince NOMME
    B = UnitsWithTrait(   pool, Daemon = 0x3fb, 3 )    # tout Daemon
    C = UnitsWithoutTrait(pool, Daemon,         3 )    # tout NON-Daemon

    pipe(X) = First( SortByFormula( Cache( Randomize(X), matchAbilityEntities = true ),
                                    UnitLevel(ActiveTarget@+0x68), ascending = false ),
                     amount = 1, ignoreForcedTargets = false )

    sel = pipe(A).Otherwise( pipe(B) ).Otherwise( pipe(C) )

    b1  = AddStaticStatModifierEffect( UnitsWithTrait(sel, Daemon, 3),
                                       EffectType.BookOfFate_DaemonBuff = 0x5ac,
                                       StatType.Attack = 0, Get(extraDmg),
                                       turns = NULL, isHidden = true )
    b2  = RemoveEffect( sel, Nullable(0x5ac), replaceableEffectType = NULL )
    b3  = Group( PerformAIAttackFromCurrentPosition( sel, utilityEntity = NULL,
                                                     customUtility = NULL,
                                                     skipAtomicCheck = false ),
                 groupEntity = sel, GroupType.Ability_Attack = 0x20 )

    return op_BitwiseAnd( op_BitwiseAnd(b1, b3), b2 )

**L'ORDRE EST LU AU DERNIER `op_BitwiseAnd`, ET IL EST LOAD-BEARING** : `(buff & attaque) & retrait`.
Le buff est POSE avant l'attaque et RETIRE apres -- c'est un buff d'UNE attaque, pas un buff
persistant. Inverser les deux derniers termes retirerait le buff avant qu'il ne serve, et l'effet
1452 ne changerait jamais aucun degat. (C'est le meme piege de forme que `VolummsMasterArtifice` vs
`DaemonfleshPlate`, transpose sur l'axe pose/retrait.)

### CASCADE `Otherwise` -- une PRIORITE a trois etages, pas un filtre

`IdunBattle.DSL.TargetsSelector$$Otherwise(primary, fallback)` = `primary` si NON VIDE, sinon
`fallback`. Le natif prend donc, DANS CET ORDRE : (1) le `thousSmnDaemonPrince` nomme par la
constante ; (2) a defaut, un Daemon quelconque ; (3) a defaut, un non-Daemon. Chacun des trois
etages est INDEPENDAMMENT randomise, cache, trie et reduit a UN element. L'i2 (<< a friendly
adjacent Summon >>) ne dit rien de cette priorite.

⚠ Le `UnitsWithTrait(sel, Daemon)` du `b1` n'est PAS redondant avec l'etage B : quand la cascade
tombe a l'etage C, `sel` est un non-Daemon et le filtre rend VIDE -> aucun buff. C'est le << If the
summon is a Daemon >> de l'i2, et c'est ce qui fait que le buff ne s'applique jamais a l'etage C.

===================================================================================================
CRITERE DE L'EMETTEUR
===================================================================================================
`On(0x26 = NormalAttack)` est un vecteur DEJA porte et peuple (`dispatch/attack.py`, consomme par
`Lakrimae`, `SuppressiveFire`, `ControlEdict`, `FullThrottle`...). L'inscription n'est donc PAS un
registered-but-dead.

===================================================================================================
FORME DU PORT (doctrine #149)
===================================================================================================
* `CreateTrigger` COLLAPSE dans `matches` (doctrine des triggers) -- sauf son dernier conjoint, qui
  est un SELECTEUR et se re-evalue donc comme un arbre ;
* `CreateBehaviour` est un ARBRE DSL integral : aucun ciblage n'est recable a la main, la cascade
  `Otherwise` et les trois etages EMERGENT des noeuds. Les feuilles appellent les Operations deja
  portees (`AddStaticStatModifierEffect`, `RemoveEffect`, `PerformAIAttack`).

RESIDUS NOMMES
  * **`UnitLevel` n'a pas de substrat** (`entities/formulas.UnitLevel`) : le dict d'unite ne porte
    pas de niveau -> la cle de tri vaut 0 partout, le tri est STABLE, l'ordre reste celui du
    `Randomize`. Fidele au regime « tous les niveaux egaux », pas au cas general. Residu `#1008-r1`.
  * **`First(..., amount = 1, ignoreForcedTargets = false)`** : le port passe par
    `First(source, index = 0)` (`PickAtIndexSelector`), qui prend le PREMIER element. Sur `amount = 1`
    les deux coincident ; `ignoreForcedTargets` n'a aucun substrat porte (aucune cible FORCEE
    n'existe dans le `State`).
  * **`Cache(..., matchAbilityEntities = true)`** : le port monte `Cache(source)` -- la memoisation
    par contexte. Le flag natif n'est lu par aucun autre call-site porte.
  * **les DEUX porteurs Thousand Sons (`thousInfernalMaster`, `thousSorcerer`) ne sont PAS
    confrontes** ici : la tranche monte `blackPossession`. Meme classe native, meme arbre -- le
    kit du porteur n'entre dans aucun noeud --, mais ce n'est pas une mesure.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import Group, op_and
from .....entities.effect_type import EffectType
from .....entities.formulas import UnitLevel
from .....entities.selectors.accessors import ActiveTarget
from .....entities.selectors.geometry import Cache, Otherwise, Randomize, UnitsWithId
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import (AdjacentFriends, First, SortByFormula,
                                           UnitsWithTrait, UnitsWithoutTrait)
from .....entities.selectors.valid_targets import HasAnyValidTarget
from .....entities.stat_type import StatType
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.effects.magnitude import ability_var
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddStaticStatModifierEffect, RemoveEffect
from ....abilities.behaviours.summon import PerformAIAttack
from ....components import UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

#: Cle du registre `RELIC_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability de relique.
ABILITY_ID = "BookOfFate"
#: `TriggeredAbilityType` 0x5b5 = 1461.
BOOK_OF_FATE = int(TriggeredAbilityType.BookOfFate)
#: `EffectType` 0x5ac = 1452, pose PUIS retire par le MEME behaviour.
DAEMON_BUFF_EFFECT = int(EffectType.BookOfFate_DaemonBuff)
DAEMON_BUFF_EFFECT_NAME = "BookOfFate_DaemonBuff"

EXTRA_DMG_KEY = "extraDmg"              # `AbilityVariableType` 8
AFFECTED_UNIT_ID_KEY = "affectedUnitId"  # `AbilityConstantType` 0x8c = 140

#: `UnitSelectionType.OnlyAliveAndTargetable = 3` -- le litteral passe aux CINQ selecteurs d'unite.
_SEL = int(UnitSelectionType.OnlyAliveAndTargetable)
#: `AdjacentFriends(Owner@+0x30, unique = true, 3)` -- le `1` du decompile est le `unique`.
_ADJACENT_UNIQUE = True
#: `Group(..., GroupType.Ability_Attack = 0x20)`.
_GROUP_ABILITY_ATTACK = 0x20
#: `AddStaticStatModifierEffect(..., StatType.Attack = 0, ..., isHidden = true)`.
_IS_HIDDEN = True


def _adjacent_summons():
    """`UnitsWithTrait( AdjacentFriends(Owner@+0x30, true, 3), UnitTrait.Summon = 2, 3 )`.

    Le MEME sous-arbre apparait dans `CreateTrigger` (sous `AmountIsGreaterThanZero`) et en tete du
    `CreateBehaviour` : le natif le RECONSTRUIT aux deux endroits (aucun `Cache` partage entre les
    deux appels), donc le port le rebatit aussi."""
    return UnitsWithTrait(AdjacentFriends(Caster(), selection_type=_SEL), int(UnitTrait.Summon),
                          selection_type=_SEL)


def _pipe(source):
    """`First( SortByFormula( Cache(Randomize(X), true), UnitLevel(ActiveTarget@+0x68), false ), 1 )`.

    `ascending = false` -> tri DESCENDANT (le plus haut niveau d'abord). Cf. le residu `UnitLevel`
    de l'en-tete : sans substrat de niveau, la cle vaut 0 partout et le tri stable preserve l'ordre
    du `Randomize`."""
    return First(SortByFormula(Cache(Randomize(source)), UnitLevel(ActiveTarget()),
                               ascending=False))


def book_of_fate_target_selector(affected_unit_id: str | None):
    """La cascade `Otherwise` a TROIS etages du `CreateBehaviour` -- MIRROR 1:1.

    `affected_unit_id` = `ConfigConstString(AbilityConstantType.affectedUnitId = 0x8c)`, resolu par
    l'appelant sur le gameconfig de l'ability (`constants.affectedUnitId`). `None`/vide -> l'etage A
    rend VIDE et la cascade tombe naturellement sur B puis C : c'est le comportement du natif quand
    aucune unite ne porte cet id, jamais un etage supprime."""
    pool = HasAnyValidTarget(_adjacent_summons(), selection_type=_SEL)
    a = _pipe(UnitsWithId(pool, affected_unit_id or "", mode=_SEL))
    b = _pipe(UnitsWithTrait(pool, int(UnitTrait.Daemon), selection_type=_SEL))
    c = _pipe(UnitsWithoutTrait(pool, int(UnitTrait.Daemon), selection_type=_SEL))
    return Otherwise(Otherwise(a, b), c)


def book_of_fate_tree(extra_dmg: int, affected_unit_id: str | None):
    """`op_BitwiseAnd( op_BitwiseAnd(b1, b3), b2 )` -- MIRROR 1:1 (cf. l'en-tete du module).

    L'ORDRE est celui du decompile : POSE du buff, PUIS attaque, PUIS retrait. Le `sel` est le MEME
    objet aux trois emplois -- le natif le partage aussi (une seule variable locale), et les `Cache`
    internes garantissent qu'il ne se re-randomise pas entre les trois."""
    sel = book_of_fate_target_selector(affected_unit_id)
    daemon_only = UnitsWithTrait(sel, int(UnitTrait.Daemon), selection_type=_SEL)
    b1 = AddStaticStatModifierEffect(daemon_only, DAEMON_BUFF_EFFECT, int(StatType.Attack),
                                     int(extra_dmg), name=DAEMON_BUFF_EFFECT_NAME)
    b3 = Group(PerformAIAttack(sel), group_id=_GROUP_ABILITY_ATTACK, targets_sel=sel)
    b2 = RemoveEffect(DAEMON_BUFF_EFFECT, sel)
    return op_and(op_and(b1, b3), b2)


def relic_vars(state: State, owner_id: int) -> "tuple[int, str | None]":
    """`(extraDmg, affectedUnitId)` au niveau de l'`AbilityState` sous lequel la relique est montee.

    `triggered_ability_state` rend le couple TERTIAIRE (`TertiaryAbilityLevel` /
    `TertiaryAbilityVariablesMultiplierPercentage`) quand `BookOfFate` arrive par l'item equipe, le
    couple PASSIF sinon -- distribution d'`UnitFactory$$Build`. Lire le couple PASSIF a la place
    ferait lire le DERNIER palier (clamp de `TryGetVariableArrayForLevel`), en silence : c'est
    exactement la faute mesuree par #1007.

    `affectedUnitId` est une CONSTANTE (`GetNumberConstant`/`ConfigConstString`), donc sans niveau :
    `ability_var(..., is_constant=True)`."""
    lvl, mult = triggered_ability_state(state, owner_id, ABILITY_ID)
    extra = ability_var(ABILITY_ID, EXTRA_DMG_KEY, lvl, multiplier_pct=mult) or 0
    affected = ability_var(ABILITY_ID, AFFECTED_UNIT_ID_KEY, is_constant=True)
    return (int(extra), None if affected is None else str(affected))


class BookOfFateAbility(TriggeredAbility):
    """`BookOfFateAbility` -- apres une ATTAQUE NORMALE du porteur, UN summon ami adjacent (priorite
    `thousSmnDaemonPrince` > Daemon > non-Daemon) attaque depuis sa position courante ; s'il est
    `Daemon`, il porte `+extraDmg` d'Attack le temps de CE coup."""

    event_id = int(EventTriggerType.NormalAttack)          # 0x26 = 38
    TRIGGERED_ABILITY_ID = BOOK_OF_FATE                    # 1461

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`On(0x26, alive) & get_OwnerIsCaster & IsAlive(Owner) & AmountIsGreaterThanZero(<summons
        adjacents>)`.

        `get_OwnerIsCaster` : sur ce vecteur, le CASTER de l'attaque normale est l'acteur.
        `IsAlive(Owner@+0x30)` est REDONDANT avec l'`ownerNeedsToBeAlive` du `On(...)` cote natif ;
        le port n'a qu'un seul canal (le `UnitComponent.alive` du porteur) et le teste une fois."""
        if ev.actor_id != self.owner_id:                   # get_OwnerIsCaster
            return False
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:              # On(..., ownerNeedsToBeAlive) & IsAlive
            return False
        # `AmountIsGreaterThanZero( UnitsWithTrait(AdjacentFriends(Owner), Summon) )` -- SELECTEUR,
        # pas formule : la surcharge lue prend un `ITargetsSelector`, donc le gate ne teste QUE la
        # PRESENCE d'un summon ami adjacent, sans rien exiger sur ses cibles.
        entities = entities_from_state(state, int(self.owner_id), ev.target_id,
                                       actor_id=ev.actor_id)
        return len(_adjacent_summons().evaluate(entities) or ()) > 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        extra_dmg, affected_unit_id = relic_vars(state, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), ev.target_id,
                                       actor_id=ev.actor_id)
        book_of_fate_tree(extra_dmg, affected_unit_id).execute(entities, ectx)
        emitted: dict = {}
        for name, payload in ectx.emitted:
            emitted.setdefault(name, []).append(payload)
        attacks = emitted.get("PerformAIAttack", ())
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "extra_dmg": int(extra_dmg), "affected_unit_id": affected_unit_id,
                "buffed": [p.get("unit") for p in emitted.get("AddEffect", ())],
                "attacks": [p.get("attacker") for p in attacks],
                "removed": len(emitted.get("RemoveEffect", ())),
                "dsl": True}
