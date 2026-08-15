"""`OrbsOfDecay` -- relique Death Guard (`TriggeredAbilityType` 0x5b9 = **1465**), volet ABILITY (#1003).

Porteurs (voie `item`, relique EQUIPABLE) : `deathBlightbringer`, `deathPutrifier`, `deathRotbone`
-- les TROIS dans `rl_duel build --list-pool` au rank courant, donc etat 2 des trois etats d'une
relique (montage ECRIT `--equip-relic`, #237).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- les TROIS artefacts natifs de l'id 1465
================================================================================================
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.OrbsOfDecayAbility$$CreateTrigger` :

    On(0x4a = AttackInAtomicGroup, ownerNeedsToBeAlive = 1)
  & get_OwnerIsCaster
  & IsMeleeAttack

⚠ **AUCUN `IsNormalAttack`** -- contraste LU avec `CalibaniteGreatsword_NormalAttackAdditionalDamage`
(meme evenement, meme namespace) qui, lui, en porte un. Le natif fait donc aussi fire 1465 sur les
autres emetteurs d'`EvaluateAbilities(0x4a)` (noeud DSL d'ability, ex. `ArmoriumCherub`), pas
seulement sur l'attaque normale.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.OrbsOfDecayAbility$$CreateBehaviour` :

    op_BitwiseAnd(
      AttackWithAttackDamage( caster  = Caster@DSLSelectors+0x48,
                              targets = Filter( AdjacentEnemies(Owner@+0x30, TargetTiles@+0x78,
                                                                unique = 1),
                                                GetTriggerForAttack(dsl, this.config@+0x20) ),
                              amount  = BaseTriggeredAbility$$MinMaxDamage(this, abilityState),
                              profile = BaseTriggeredAbility$$GetDamageProfile(this),
                              hits    = BaseTriggeredAbility$$GetHits(this),
                              source  = AbilityOrEffect(this), options = <struct ZEROEE>,
                              selectionType = 2 ),
      AddEffect( 0x4dc = 1244 Contaminated, AbilityStateReference,
                 targets = TargetTiles@+0x78, turns = null ) )

`...OrbsOfDecayAbility$$GetTriggerForAttack(dsl, config)` -- STATIQUE, et c'est le pivot de la
tranche : le MEME artefact est reutilise par l'effet 1463 (cf. plus bas).

    AmountIsGreaterThanZero( StatAmount(Subject@+0x68, 0x10 = FixedArmor, statPart 3 = Initial,
                                        modificationEntity = null, selectionType = 0) )
  & AmountIsGreater( Divide( Multiply( StatNegativeModification(Subject@+0x68, 0x10 = FixedArmor),
                                       <DSLFormulas+0x30> = Direct(100) ),
                             StatAmount(...ci-dessus...), mode 0 = half-to-even ),
                     ConfigConst(0x83 = armorReductionPct, config) )

= « les ennemis dont l'armure de BASE est > 0 et dont la SOMME des reductions d'armure depasse
STRICTEMENT `armorReductionPct` % de cette base ».

CE QUI A ETE QUALIFIE AVANT DE PORTER (le residu `#998-r2` l'exigeait explicitement) :
  * `0x10` = `StatType.FIXED_ARMOR` (16) -- meme litteral que le predicat de ciblage deja porte de
    `PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger` (`HasNegativeModifier(subject, 0x10)`
    + `StatAmount(subject, 0x10, part 3)`), et que le filtre `ARMOR_STAT_TYPES` de `stats.py` ;
  * `<DSLFormulas+0x30>` = `Direct(100)` -- LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`,
    deja cite par `effects/loki/hits.py` et `effects/loki/daemonic_patrons.py` ;
  * `statPart 3` = `StatPart.INITIAL` -> le denominateur est l'armure de BASE, pas l'armure
    COURANTE. C'est ce qui rend le ratio lisible comme un « % de reduction », conforme a l'i2 ;
  * `StatNegativeModification` != `StatAmount(part 5 = MODIFICATION)` : la formule native
    (`IdunBattle.Entities.Formulas.NegativeStatModificationFormula$$Calculate`) itere le
    `Dictionary<source, ValueModification>` et n'accumule QUE les contributions `< 0`, en valeur
    absolue -- un `-40` compense par un `+40` rend `40`, la ou le total signe rend `0`.

⚠ **`AmountIsGreater` est STRICT** (classe native distincte d'`AmountIsEqualOrGreater`, cf.
`entities/triggers.py`), alors que l'i2 dit « reduced by 30% **or more** ». Le decompile fait foi :
une cible dont l'armure est reduite d'EXACTEMENT 30 % n'est PAS retenue. C'est le cas discriminant
du cliquet offline -- et il n'est pas theorique, `ContaminatedStatModifierEffect` pose precisement
`-ContaminatedArmorReductionPct = -30 %`.

`IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies` -- surcharge VARIANTE B tranchee par les
XREFS ENTRANTES (`180eac190`, dont `OrbsOfDecayAbility$$CreateBehaviour` est appelant ; l'autre
surcharge `180eac220` ne l'a PAS pour appelant) :

    AdjacentEnemies(this, unit, unitTile, unique)
      = Enemies(unit, Units(AdjacentTiles(unitTile), unique, 3) op_Subtraction unitTile, 3)

et `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` EXCLUT ses tuiles d'origine (la
boucle teste `Contains(originTiles, adjacentTile)` avant d'ajouter). Donc :
**la CIBLE de l'attaque n'est PAS frappee par ce volet** -- seuls ses VOISINS le sont.

C'EST L'AUTRE MOITIE DE L'i2, ET ELLE VIT DANS UN AUTRE ARTEFACT.
« enemy units that ... are also **on or** adjacent to the target's hex » : le « on » est
`IdunBattle.Entities.Effects.Loki.OrbsOfDecay_AdditionalHitsEffect$$CreateAdditionalHits`, qui
ajoute des COUPS a l'attaque primaire elle-meme avec le MEME predicat :

    EffectAdditionalHits.Create( get_OwnerIsCaster & GetTriggerForAttack(dsl, config) & IsMeleeAttack,
                                 GetMinMaxDamage(this, 0), 1, config.GetDamageProfile(),
                                 ConfigConst(0x2f = nrOfHits, config), <0>, GetMinMaxDamage(this, 1) )

et `...OrbsOfDecay_AdditionalHitsAbility$$GetEffectType` rend `0x5b7` = **1463** : une SECONDE
classe native du meme id 1465, de la famille `AOwnerEffectTriggeredAbility`, qui pose cet effet sur
son porteur. **Ce volet n'est PAS porte par cette tranche** -- il tombe dans le canal
`additional_hit_groups` (#179), foyer `entities/effects/loki/hits.py`, et c'est EXACTEMENT le
residu deja ouvert `#884-r2` (« trois descripteurs natifs `Average` ne sont PAS portes », qui nomme
`OrbsOfDecay_AdditionalHitsEffect`). Residu `#1003-r1` : le cabler.

================================================================================================
FORME DU PORT (doctrine #149)
================================================================================================
* `CreateTrigger` COLLAPSE imperativement dans `matches` (patron de tous les `On(0x4a)` portes) ;
* `CreateBehaviour` est un ARBRE DSL : le `Filter` + son predicat sont des NOEUDS, jamais du
  ciblage recable a la main -- c'est ce qui permet au meme predicat de resservir tel quel a #1003-r1.

CE QUE `RELIC_ABILITY_TRIGGERS` N'EXIGE PAS : 1465 est une `TriggeredAbilityType`, donc elle
n'entre NI dans `ABILITY_CLASSES`, NI dans `TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE` --
ces trois registres sont ceux des abilities ACTIVES.

RESIDUS NOMMES
  * **`#1003-r1`** -- le volet `OrbsOfDecay_AdditionalHits` (effet 1463) ci-dessus.
  * **rang / portee de l'emetteur** : le port n'emet `On(0x4a)` que depuis
    `DamageHandler.visit_AttackUnitMessage` (voie MESSAGE de l'attaque normale) et depuis le noeud
    DSL `EvaluateAbilities`. Les portes qui appellent `AttackDamageOperation.execute` DIRECTEMENT
    (overwatch, `UseActiveAbility`, IA de summon) ne l'emettent pas -- MEME residu que `#478-r3`,
    et il preexiste a cette tranche.
  * **`selectionType = 2`** (9e argument d'`AttackWithAttackDamage`) n'a pas d'equivalent dans la
    feuille portee : celle-ci resout ses cibles par le selecteur, deja filtre en `3 =
    OnlyAliveAndTargetable` aux DEUX etages de la variante B. Non modelise, comme sur tous les
    autres call-sites portes de cette feuille.
"""
from __future__ import annotations

from fractions import Fraction as _Fraction
from typing import Optional

from .....dsl.base import Const, _round_fix64
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.formulas import (Divide, Multiply, StatAmount, StatNegativeModification)
from .....entities.selectors.accessors import Subject, TargetTile
from .....entities.selectors.units import AdjacentEnemies, Filter
from .....entities.stats import StatPart, StatType
from .....entities.triggers import AmountIsGreater, AmountIsGreaterThanZero, TriggerAnd
from .....entities.effects.magnitude import ability_var
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....state import State
from .....entities.behaviours import op_and
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `RELIC_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability (l'item relique
#: `R_*_OrbsOfDecay` la materialise dans `BC.Units[].TertiaryAbility`).
ABILITY_ID = "OrbsOfDecay"

#: `constants.damageProfile` de 1465 -- LU au gameconfig, pas deduit du nom.
DAMAGE_PROFILE = "Toxic"
#: `ConfigConst(0x83 = armorReductionPct)`. La constante n'est pas indexee par niveau
#: (`AbilityConfiguration$$GetNumberConstant`), donc elle se resout une fois a la construction de
#: l'arbre -- meme idiome que les autres `ConfigConst` du runner (`behaviours/stats.py`).
ARMOR_REDUCTION_PCT_KEY = "armorReductionPct"
#: `AddEffect(0x4dc = 1244 Contaminated, ...)`.
CONTAMINATED = int(EffectType.Contaminated)
#: `3` EN DUR aux deux etages de la variante B d'`AdjacentEnemies` (`Units(..., 3)` et `Enemies(..., 3)`).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)
#: `StatAmount(..., 0x10, 3, ...)` / `StatNegativeModification(..., 0x10)`.
FIXED_ARMOR = int(StatType.FIXED_ARMOR)
INITIAL = int(StatPart.INITIAL)
#: `Divide(..., ..., 0)` -- mode 0 = arrondi Fix64 half-to-even (le litteral natif).
DIVIDE_MODE_HALF_EVEN = 0
#: `<DSLFormulas+0x30>` = `Direct(100)`, LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`.
PERCENT_BASE = 100


def armor_reduction_pct() -> int:
    """`ConfigConst(0x83 = armorReductionPct, config@+0x20)` = `constants.armorReductionPct` de 1465."""
    return int(ability_var(ABILITY_ID, ARMOR_REDUCTION_PCT_KEY, is_constant=True) or 0)


def orbs_of_decay_trigger_for_attack():
    """`...OrbsOfDecayAbility$$GetTriggerForAttack(dsl, config)` -- MIRROR 1:1, evalue sur le SUJET
    (`Subject@DSLSelectors+0x68`, l'element courant lie par le `Filter`).

    L'ORDRE DE LA CONJONCTION EST CELUI DU NATIF, et il porte : `AmountIsGreaterThanZero(armure de
    base)` d'ABORD, `AmountIsGreater(ratio, seuil)` ENSUITE. `TriggerAnd` court-circuite (comme
    `AbilityTrigger$$op_BitwiseAnd`), donc le `Divide` n'est jamais evalue quand le denominateur est
    nul -- ce qui est la seule raison pour laquelle un arbre natif peut diviser par `StatAmount`
    sans garde."""
    initial_armor = StatAmount(Subject(), FIXED_ARMOR, INITIAL)
    reduction = StatNegativeModification(Subject(), FIXED_ARMOR)
    ratio = Divide(Multiply(reduction, Const(PERCENT_BASE)), initial_armor,
                   DIVIDE_MODE_HALF_EVEN)
    return TriggerAnd(AmountIsGreaterThanZero(initial_armor),
                      AmountIsGreater(ratio, Const(armor_reduction_pct())))


def orbs_of_decay_armor_gate(initial_fixed_armor, negative_modification) -> bool:
    """LE MEME `...OrbsOfDecayAbility$$GetTriggerForAttack`, sous forme SCALAIRE.

    POURQUOI DEUX EXPRESSIONS. L'arbre ci-dessus vit dans un `Filter` (le volet ABILITY resout
    des ENTITES) ; le volet `OrbsOfDecay_AdditionalHits` (#884-r2 / #1003-r1), lui, est un
    descripteur du canal #179, evalue depuis `additional_hit_groups(ctx)` -- un DICT, sans
    `ExecutionContext` ni entites. Le natif, lui, appelle LA MEME fonction statique des deux
    endroits (`OrbsOfDecay_AdditionalHitsEffect$$CreateAdditionalHits` la reference
    explicitement). Les deux expressions du port doivent donc rester d'accord : c'est ce que
    garde `tests/engine/test_884r2_orbs_of_decay_offline.py` etage 2, qui balaie le couple
    (armure initiale, reduction) et confronte les deux formes.

    Le corps est le mirror LITTERAL, dans l'ordre du natif :
        AmountIsGreaterThanZero( StatAmount(subject, FixedArmor, Initial) )
      & AmountIsGreater( Divide(Multiply(StatNegativeModification(subject, FixedArmor), 100),
                                <l'armure initiale>, mode 0 = half-to-even),
                         ConfigConst(0x83 = armorReductionPct) )

    ⚠ `AmountIsGreater` est STRICT (l'i2 dit « or more », le decompile dit « > ») -- et le cas
    discriminant n'est pas theorique : `ContaminatedStatModifierEffect` pose exactement
    `-armorReductionPct %`.
    ⚠ Le court-circuit du premier conjoint est LOAD-BEARING : c'est la seule raison pour laquelle
    l'arbre natif peut diviser par `StatAmount` sans garde.
    ⚠ TRI-ETAT : un scalaire NON MESURE (`None`) ferme le gate -- jamais un 0 rabattu, qui ferait
    passer une cible sans armure pour une cible non reduite (ou l'inverse)."""
    if initial_fixed_armor is None or negative_modification is None:
        return False
    initial = int(initial_fixed_armor)
    if initial <= 0:                                   # AmountIsGreaterThanZero -> court-circuit
        return False
    ratio = _round_fix64(_Fraction(int(negative_modification) * PERCENT_BASE, initial),
                         DIVIDE_MODE_HALF_EVEN)
    return int(ratio) > armor_reduction_pct()          # AmountIsGreater, STRICT


def orbs_of_decay_targets():
    """`Filter( AdjacentEnemies(Owner@+0x30, TargetTiles@+0x78, unique = 1), GetTriggerForAttack )`.

    `AdjacentEnemies(<ancre TUILE>, <rayon>, selection_type)` est la forme portee de la VARIANTE B
    (3e argument = une ENTITE/ancre geometrique, pas un booleen) -- MEME lecture que
    `abilities/loki/additional_targets.py` (TalonOfHorus) et
    `triggers/loki/calibanite_greatsword.py`, qui appellent la MEME surcharge. L'ancre est ici
    `TargetTiles@+0x78` (l'empreinte de la CIBLE), pas `CasterTile` : le balayage est centre sur la
    cible, et la reference d'EQUIPE reste l'Owner (== le caster sur cette ability, dont le trigger
    porte `get_OwnerIsCaster`).

    Le `unique = 1` natif tombe sur le parametre RAYON du noeud porte, qui vaut 1 : les deux
    coincident en valeur, et le rayon EST 1 par construction (`AdjacentTiles` = la liste d'adjacence
    STOCKEE). Meme mappage que `calibanite_greatsword.sweep_additional_targets`."""
    return Filter(AdjacentEnemies(TargetTile(), Const(1), selection_type=SELECTION),
                  orbs_of_decay_trigger_for_attack())


def orbs_of_decay_tree():
    """`...OrbsOfDecayAbility$$CreateBehaviour` = `op_BitwiseAnd(attaque, contamination)`, dans CET
    ordre.

    * l'attaque route `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille
      ATTACK : crit/block, 2 tirages/coup) -> `native_factory="attack"`, le defaut ;
    * `is_melee=False` : `attackRangeType` de 1465 vaut **`Ranged`** au gameconfig. Le trigger, lui,
      exige `IsMeleeAttack` -- mais c'est la nature de l'attaque DECLENCHANTE, pas celle du coup
      pose ici. Les deux litteraux sont LUS, et ils ne sont pas le meme ;
    * `multi=True` : le natif passe un SELECTEUR multi-cible a `AttackWithAttackDamage`, donc
      `AttackBehaviour$$Execute` resout la liste, l'`OrderBy` puis attaque chaque cible ;
    * `level_slot="tertiary"` : `MinMaxDamage` se resout contre l'`abilityState` sous lequel
      l'ability est MONTEE, et une relique EQUIPEE arrive par la branche TERTIAIRE d'
      `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` (couple
      `TertiaryAbilityLevel` / `TertiaryAbilityVariablesMultiplierPercentage`). Lire le slot PASSIF
      donnerait 50 sur tout runner normalise, donc le dernier palier de `minDmg`/`maxDmg`, quel que
      soit le niveau REEL de la relique -- l'ecart silencieux que #357 a ferme pour `DawnBlade` ;
    * `AddEffect` avec **`source_from_target=True`** : la surcharge appelee est celle a 5 arguments
      (`IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns)`,
      `180e9eb30`), dont le corps passe litteralement `0` en SOURCE a `AddEffectBehaviour$$.ctor` ->
      chaque TUILE contaminee est sa PROPRE source. C'est le discriminant EXACT d'avec
      `Lakrimae_AddContamination`, qui appelle la surcharge a 6 arguments avec `source = Owner@+0x30` ;
    * `turns = null` -> `duration_rounds=None` = duree `DefaultAmountOfRounds(0x4dc)` de l'effet."""
    attack = AttackWithAttackDamage(
        orbs_of_decay_targets(), ABILITY_ID, DAMAGE_PROFILE, is_melee=False, multi=True,
        level_slot="tertiary", ability_type=int(TriggeredAbilityType.OrbsOfDecay))
    contaminate = AddEffect(CONTAMINATED, EffectType.Contaminated.name, TargetTile(),
                            duration_rounds=None, source_from_target=True)
    return op_and(attack, contaminate)


class OrbsOfDecayAbility(TriggeredAbility):
    """`...OrbsOfDecayAbility` (triggered 0x5b9 = 1465) -- cf. l'en-tete du module.

    OBSERVABLE : sur toute attaque de MELEE du porteur, (1) une attaque `Toxic` `nrOfHits`x contre
    les ennemis ADJACENTS a la tuile de la cible dont l'armure est reduite de PLUS de
    `armorReductionPct` % de sa base, et (2) `Contaminated` sur la ou les tuiles de la cible --
    ce second volet est INCONDITIONNEL."""
    event_id = int(EventTriggerType.AttackInAtomicGroup)      # `On(0x4a, ownerNeedsToBeAlive = 1)`
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.OrbsOfDecay)          # 0x5b9 = 1465

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` : sur ce vecteur, l'`AbilityEntities` natif porte le MEME entite en
        # `Caster@+0x48` et en `Actor@+0x40` (l'emetteur est la passe d'attaque du caster lui-meme),
        # et le port ne thread qu'`actor_id` -- collapse fidele sur CE vecteur, pas en general.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        if ev.target_id is None:
            return False
        # `IsMeleeAttack` -- nature du coup DECLENCHANT, threadee telle quelle par l'emetteur.
        # ⚠ Pas de gate `IsNormalAttack` : le natif n'en porte AUCUN (cf. l'en-tete).
        return not ev.ranged

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id)
        orbs_of_decay_tree().execute(entities, ectx)
        hits = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        contam = [p for n, p in ectx.emitted if n == "AddEffect"]
        if not hits and not contam:
            return None
        return {"relic": ABILITY_ID, "owner": int(self.owner_id), "target": int(ev.target_id),
                "splash": [{"target": p.get("target"), "attack": p.get("attack")} for p in hits],
                "contaminated": [{"tile": p.get("target"), "placed": p.get("placed")}
                                 for p in contam]}
