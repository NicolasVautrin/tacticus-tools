"""`EcogSupport` (`TriggeredAbilityType` 0x5cf = **1487**), passif de `votanIronmaster` << Vynn >>
(HERO Leagues of Votann, HORS pool par defaut -> injection catalogue) -- canal **T**
(`ABILITY_TRIGGERS`).

i2 (L50) : « Whenever Vynn repairs a friendly unit, he summons an E-COG in a free adjacent hex.
Cannot have more than 3 E-COGs summoned this way at the same time. Vynn can repair other friendly
units even if they are at full Health. [...] if he repairs a friendly unit while 3 summoned E-COGs
are already on the battlefield, one random summoned E-COG adjacent to Vynn also performs a repair,
if possible. »

UN nom de kit, **DEUX classes natives** (forme `LetTheGalaxyBurn` / `FuryFromTheDelve`), mais ici
elles ne se ventilent PAS sur un `triggerType` : ce sont deux `BaseTriggeredAbility` distinctes,
avec deux `CreateTrigger` differents.

================================================================================================
LES DEUX CORPS, LUS VERBATIM SUR `rnca9r7q6c`
================================================================================================

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ECogSupport_InitAbility`

    $$CreateTrigger   = OnOwnerSpecificAbilityInit(0x5cf = 1487)
    $$CreateBehaviour = DSLBehaviors.AddFlag( Owner@DSLSelectors+0x30, 0x18 )

`UnitFlag 0x18 = 24 = CanRepairFullHealthUnits` (`data/symbols/<build>/frida/enums.tsv`).
**CE VOLET N'EST PAS DANS CE MODULE** : il n'a ni event ni behaviour a rejouer, c'est un etat POSE
A L'INIT. Il vit donc sur le canal des inits (`entities/effects/factory.ABILITY_INIT_OWNER_FLAGS`,
seede par `runner/operations/spawn._seed_ability_owner_effects`), exactement comme les
owner-effects de la meme boucle native `InitializeActorAbilitiesOperation$$Execute`.
⚠ Ce n'est PAS un port inerte : son LECTEUR existait deja
(`runner/abilities/attack_query.entity_can_be_repaired`, 4e disjunct du gate d'eligibilite).

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ECogSupportAbility$$CreateTrigger`

    On( 0x30 = 48 UnitRepaired, ownerNeedsToBeAlive: 1 )  op_BitwiseAnd  get_OwnerIsCaster

## `...ECogSupportAbility$$CreateBehaviour(abilityState, triggerType)`

UN SEUL arbre (aucune ventilation sur `triggerType`), et les trois helpers sont INLINES dans le
corps -- ils existent AUSSI comme methodes nommees, dont les corps sont mot pour mot identiques
(`$$AlreadySummonedUnits`, `$$GetPossibleTriggerRepairSummons`, `$$SummonTargetTile`) :

    If( DSLTriggers.AmountIsGreater( DSLFormulas.ConfigConst(0x3c = maxSummons, config),
                                     DSLFormulas.Count( AlreadySummonedUnits() ) ),

        DSLBehaviors.Spawn( Owner@+0x30,
                            SummonTargetTile(),
                            GetStringConstant(0 = unitId),
                            SpawnUnitOptions.WithStatsFromConfig(config, abilityState, 0, 0) ),

        DSLBehaviors.PerformAIAbility( PickRandomly(GetPossibleTriggerRepairSummons(),
                                                    1, 0, int.MaxValue, false),
                                       getAbilityType   = <>c.<CreateBehaviour>b__3_0,
                                       allowOnlyMove    = 0,
                                       overrideMovement = <DSLFormulas+0x18 = Direct(0)>,
                                       utilityEntity    = 0, customUtility = 0 ) )

    AlreadySummonedUnits()            = UnitsWithId( Children(Owner@+0x30),
                                                     GetStringConstant(0),
                                                     3 = OnlyAliveAndTargetable )

    GetPossibleTriggerRepairSummons() = UnitsWithAnyValidTarget(
                                            UnitsWithId(Children(Owner@+0x30), unitId, 3)
                                              op_BitwiseAnd AdjacentFriends(Caster@+0x48,
                                                                            unique: 1, 3),
                                            UnitNormalRepairType( ActiveTarget@+0x68 ) )

    SummonTargetTile()                = PickRandomly( CanAddUnit(AdjacentTiles(Owner@+0x30)),
                                                      1, 0, int.MaxValue, false )

Gameconfig `passiveAbilities.EcogSupport` : `maxSummons = 3`, `unitId = "votanSmnEcog"`, variables
`summonHp` / `summonDmg` / `summonArmor`.

`AmountIsGreater(maxSummons, count)` ⇒ `then` = SPAWN, `else` = faire REPARER un E-Cog existant.
Le texte i2 et le decompile concordent branche par branche.

================================================================================================
CINQ LECTURES QUI NE SE DEVINENT PAS
================================================================================================

1. **`If` est ici la surcharge `abilityTrigger`, PAS la surcharge `formula`.** Tranche par le TYPE
   de l'argument au call-site : `DSLTriggers$$AmountIsGreater` rend un `IAbilityTrigger`. La
   surcharge `formula` (celle qu'appelle `FuryFromTheDelveAbility$$CreateBehaviour`) enveloppe son
   argument dans `AmountIsGreaterThanZero` ; ici il n'y a rien a envelopper. Les TROIS surcharges
   sont homonymes -- recopier le voisin de forme ecrirait un test `> 0` sur un booleen deja calcule.

2. **`UnitNormalRepairType` prend `ActiveTarget@+0x68`, pas `Owner` ni `Caster`.** C'est ce qui rend
   le filtre PAR E-COG : `IdunBattle.Entities.Selectors.UnitsWithAnyValidTargetSelector$$Select`
   ECRIT l'unite courante dans `AbilityEntities+0x20` AVANT d'evaluer le selecteur d'ability, et
   `+0x20` EST le slot `activeTarget` (`ActiveTargetSelector$$Select` le lit, avec repli sur
   `+0x10` ; `PreviousActiveTargetSelector$$Select` lit `+0x28`).
   ⚠ **Le depot citait `+0x68` de DEUX facons contradictoires** : `runner/abilities/admec.py` et
   `.../triggers/loki/synaptic_linchpin.py` disent `ActiveTarget` (juste),
   `.../triggers/loki/fury_from_the_delve.py` disait `Current` (faux, corrige par #964-r1). Un
   sélecteur `Current` n'existe d'ailleurs nulle part, ni au natif ni au port.

3. **Le `Func<IEntity,int>` de `PerformAIAbility` n'est PAS l'attaque normale.** C'est
   `...ECogSupportAbility.u003Cu003Ec$$u003CCreateBehaviouru003Eb__3_0`, dont le corps ENTIER est
   `IdunBattle.Entities.UnitExtensions$$GetRepairType(e)` = `<ActiveAbilityComponent>+0x2c`. Les
   quatre AUTRES noeuds de cette famille CACHENT leur `Func` dans un `<>c` et il vaut
   `GetNormalAttackType` (`+0x28`) : le port le codait donc en dur, et le laisser tel quel aurait
   fait ATTAQUER l'E-Cog au lieu de le faire REPARER. Le champ `+0x68` est desormais threade
   (`behaviours/ai_control.PerformAIAbility(get_ability_type=...)`), `None` = le comportement
   d'avant pour les huit appelants anterieurs.

4. **`overrideMovement = Direct(0)`, et ce n'est pas un `null`.** `DSLFormulas+0x18` est la
   constante `Direct(0)` (`IdunBattleLogic.Entities.DSLFormulas$$.ctor` : `+0x18 = Direct(0)`,
   `+0x20 = Direct(1)`, `+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`). Passe
   tel quel a `ABaseAiUnitTactic$$GenerateActionTiles(unit, true, maxDistance)`, `0` = **la tuile
   COURANTE seule**. L'E-Cog repare SANS BOUGER. Un `null` ouvrirait sa plage de deplacement
   normale -- ecart observable, pas cosmetique.

5. **Le cap compte les enfants VIVANTS ET CIBLABLES** (`UnitSelectionType.OnlyAliveAndTargetable`
   = 3), et `Children` ne filtre RIEN : sans le mode, un E-Cog mort tiendrait un slot que le natif
   a libere. Meme piege que `SynapticLinchpin`, et meme foyer de filtre.

================================================================================================
CRITERE DE L'EMETTEUR
================================================================================================
`On(0x30 = 48 UnitRepaired)` : l'emetteur N'EXISTAIT PAS -- `runner/operations/repair.py` nommait
ce vecteur parmi ses non-portes. Il est ajoute par la meme tranche
(`triggers/dispatch/repair.py::unit_repaired_triggers`), a sa place native : APRES la mutation
`FillUp` et APRES le gate de sortie anticipee. Sans lui, inscrire cette classe au registre aurait
produit un *registered-but-dead* parfait -- le mode de panne que le critere de l'emetteur existe
pour attraper.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.behaviours import If
from .....entities.formulas import Count, UnitNormalRepairType
from .....entities.selectors.accessors import ActiveTarget, Owner
from .....entities.selectors.geometry import PickRandomly, UnitsWithId
from .....entities.selectors.tiles import AdjacentTiles, CanAddUnit, Caster, ChildrenOf
from .....entities.selectors.units import AdjacentFriends, And
from .....entities.selectors.valid_targets import UnitsWithAnyValidTarget
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsGreater
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.behaviours.ai_control import PerformAIAbility
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.summon import Spawn
from ....components import UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig de la passiveAbility porteuse.
ECOG_SUPPORT = "EcogSupport"
#: `OnOwnerSpecificAbilityInit(0x5cf)` / `AbilityOrEffect(0x5cf)`.
ECOG_SUPPORT_ID = int(TriggeredAbilityType.EcogSupport)                   # 0x5cf = 1487

#: `On(0x30 = 48 UnitRepaired, ownerNeedsToBeAlive = 1)`.
_ON_UNIT_REPAIRED = int(EventTriggerType.UnitRepaired)                    # 0x30 = 48

#: `GetNumberConstant(0x3c)` / `GetStringConstant(0)` -- des CONSTANTES de config, jamais des
#: variables indexees par le niveau : le natif n'appelle pas `GetVariableForLevel` ici.
_MAX_SUMMONS_KEY = AbilityConstantType.maxSummons.name                    # 0x3c = 60
_UNIT_ID_KEY = AbilityConstantType.unitId.name                            # 0x0

#: `UnitSelectionType.OnlyAliveAndTargetable` -- le 3e argument des trois selecteurs d'unite.
_ALIVE_AND_TARGETABLE = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


def _config(key: str, default=None):
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` / `$$GetStringConstant`
    sur la config de CE passif. Les deux cles lues vivent dans `constants` (pas dans `variables`).

    ⚠ On ne passe PAS par le noeud `ConfigConst` du port : sa docstring porte une RESERVE explicite
    (il appelle `get_variable_for_level`, donc il fait le travail de `ConfigVar`, pas celui de
    `ConfigConst`). Meme lecture directe que `fury_from_the_delve._ability_constant`."""
    import gameconfig as GC
    cfg = (GC.ability(ECOG_SUPPORT) or {}).get("constants") or {}
    return cfg.get(key, default)


def _max_summons() -> int:
    """`GetNumberConstant(0x3c = maxSummons)` = 3. Illisible -> 0, qui ferme la branche SPAWN (le
    natif compare `maxSummons > count`, et `0 > n` est faux des le premier E-Cog)."""
    try:
        return int(_config(_MAX_SUMMONS_KEY))
    except (TypeError, ValueError):
        return 0


def already_summoned_units():
    """`...ECogSupportAbility$$AlreadySummonedUnits` =
    `UnitsWithId( Children(Owner@+0x30), GetStringConstant(0), 3 )`.

    `Children(parent)` cote natif = `ChildrenOf` cote port (l'accumulateur `Children` du cast
    courant est un AUTRE noeud) : ce sont les entites dont le PARENT est Vynn, mortes comprises --
    d'ou le mode `3`, qui est ici load-bearing."""
    return UnitsWithId(ChildrenOf(Owner()), _config(_UNIT_ID_KEY), _ALIVE_AND_TARGETABLE)


def get_possible_trigger_repair_summons():
    """`...ECogSupportAbility$$GetPossibleTriggerRepairSummons` =

        UnitsWithAnyValidTarget(
            UnitsWithId(Children(Owner@+0x30), unitId, 3)
              op_BitwiseAnd AdjacentFriends(Caster@+0x48, unique: 1, 3),
            UnitNormalRepairType( ActiveTarget@+0x68 ) )

    L'INTERSECTION (`op_BitwiseAnd` sur `TargetsSelector` = le noeud `And`) : « mes E-Cogs » ET
    « les allies adjacents a Vynn ». Puis le filtre de CIBLAGE, evalue par E-Cog avec l'E-Cog pose
    en `ActiveTarget` -- cf. le point 2 de l'en-tete."""
    mine = UnitsWithId(ChildrenOf(Owner()), _config(_UNIT_ID_KEY), _ALIVE_AND_TARGETABLE)
    adjacent = AdjacentFriends(Caster(), selection_type=_ALIVE_AND_TARGETABLE)
    return UnitsWithAnyValidTarget(And(mine, adjacent), UnitNormalRepairType(ActiveTarget()),
                                   selection_type=_ALIVE_AND_TARGETABLE)


def summon_target_tile():
    """`...ECogSupportAbility$$SummonTargetTile` =
    `PickRandomly( CanAddUnit(AdjacentTiles(Owner@+0x30)), 1, 0, int.MaxValue, false )`.

    ⚠ Le `PickRandomly` reste ICI, dans le tile-selecteur, et n'est PAS remonte en `pick_n` de la
    feuille `Spawn` : les deux ecritures sont equivalentes en valeur, mais le natif ENVELOPPE le
    selecteur de tuiles, et c'est cette forme que le mirror cite."""
    return PickRandomly(CanAddUnit(AdjacentTiles(Owner())), 1, False, 0x7FFFFFFF, False)


def _repair_type_of(state: State, unit_id: int) -> Optional[int]:
    """Le `Func<IEntity,int>` `+0x68` = `IdunBattle.Entities.UnitExtensions$$GetRepairType(e)`,
    materialise pour `PerformAIAbility` (point 3 de l'en-tete).

    Meme substrat que le noeud VALEUR `entities/formulas.UnitNormalRepairType` -- une seule lecture
    du champ, deux points d'appel (le filtre de selection, puis l'ability jouee)."""
    from ....abilities.behaviours.context import entities_from_state as _efs
    ents = _efs(state, int(unit_id), None)
    return UnitNormalRepairType(Owner()).calculate(ents)


def ecog_support_tree(max_summons: int, ability_state: tuple | None = None) -> If:
    """L'arbre ENTIER de `ECogSupportAbility$$CreateBehaviour` (verbatim natif : en-tete du module).

    `ability_state` = le 2e argument de `SpawnUnitOptions$$WithStatsFromConfig`, sous lequel l'E-Cog
    monte SES propres abilities et lit `summonHp`/`summonDmg`/`summonArmor`."""
    cap_libre = AmountIsGreater(Const(int(max_summons)), Count(already_summoned_units()))
    spawn = Spawn(summon_target_tile(), ECOG_SUPPORT, ability_state=ability_state)
    repair = PerformAIAbility(
        PickRandomly(get_possible_trigger_repair_summons(), 1, False, 0x7FFFFFFF, False),
        # `overrideMovement = Direct(0)` : la tuile COURANTE seule, l'E-Cog ne se deplace pas.
        override_movement=Const(0),
        allow_only_move=False,
        get_ability_type=_repair_type_of)
    return If(cap_libre, spawn, repair)


class ECogSupportAbility(TriggeredAbility):
    """`ECogSupportAbility` (triggered 1487) -- a chaque REPARATION dont Vynn est le caster : soit un
    E-Cog de plus apparait sur une tuile libre adjacente (tant que `maxSummons > <E-Cogs vivants>`),
    soit un E-Cog deja pose, adjacent a Vynn et ayant une cible valide, repare a son tour SANS
    bouger. Arbre natif des deux faces : en-tete du module."""

    event_id = _ON_UNIT_REPAIRED
    TRIGGERED_ABILITY_ID = ECOG_SUPPORT_ID

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` = `AreEqual(Owner@+0x30, Caster@+0x48)`. Sur ce vecteur le natif passe
        # le REPARATEUR dans les deux premiers slots du `processor.<slot 0x51>` -- c'est donc
        # `ev.actor_id` qui porte le caster (cf. `dispatch/repair.py`).
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        if ev.target_id is None or state.get_entity(ev.target_id) is None:
            return False
        owner = state.get_entity(self.owner_id)
        uc = owner.get_component(UnitComponent) if owner is not None else None
        return uc is not None and bool(uc.alive)          # `On(..., ownerNeedsToBeAlive = 1)`

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ability_state = self._ability_state(state)
        ents = entities_from_state(state, int(self.owner_id), ev.target_id, actor_id=ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        ecog_support_tree(_max_summons(), ability_state=ability_state).execute(ents, ectx)
        spawned = [p.get("unit") for n, p in ectx.emitted if n == "SpawnUnit"]
        repaired = [p for n, p in ectx.emitted if n == "PerformAIAbility"]
        if not spawned and not repaired:
            return None                                   # aucune branche n'a mordu -> no-op
        return {"passive": ECOG_SUPPORT, "unit": int(self.owner_id),
                "target": int(ev.target_id), "max_summons": _max_summons(),
                "spawned": spawned,
                "repair_acted": (repaired[0].get("acted") if repaired else None),
                "dsl": True}

    def _ability_state(self, state: State) -> tuple:
        """L'`AbilityState` du PASSIF du porteur -- celui que `CreateBehaviour` recoit et qui part
        dans `SpawnUnitOptions$$WithStatsFromConfig`. Sans lui, l'E-Cog lirait ses stats a
        l'index 0 (mode de panne #174)."""
        from ....components import StatsComponent
        e = state.get_entity(self.owner_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = getattr(sc, "ctx", None)
        level = getattr(ctx, "passive_ability_level", None)
        if level is None:
            level = getattr(ctx, "active_ability_level", None)
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        return level, mult
