"""`LegacyOfCombat` (`TriggeredAbilityType` 0x527 = 1319, passif de `custoBladeChampion`
<< Kariyan >>, Adeptus Custodes) -- l'attaque SUPPLEMENTAIRE qui suit la PREMIERE attaque du tour.
Tache #928, face COMBAT. Ferme le residu `#509-r1`.

i2 `Abilities/LegacyOfCombat_CurrentLevelDescription` : << After performing his first attack each
turn, Kariyan performs an additional attack. If he is adjacent to an enemy **Big Target**, this
attack deals {nrOfHits_2}x {minDmg_2}-{maxDmg_2} **Piercing** Damage to it. If there is no adjacent
enemy Big Target, Kariyan deals {nrOfHits}x {minDmg}-{maxDmg} **Power** Damage to **each** adjacent
enemy instead. >>

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite, live = confirmation
================================================================================================

Slots `DSLFactory` (`this@+0x28`) : `+0x78 Behaviors`, `+0x80 Formulas`, `+0x88 Triggers`,
`+0x90 Selectors` ; slots `DSLSelectors` : `+0x30 Owner`, `+0x48 Caster`, `+0x60 Target`.

## 1. `...LegacyOfCombatAbility$$CreateTrigger` -- conjonction de QUATRE termes

    On( 0xb = EventTriggerType.UnitAbility, ownerNeedsToBeAlive = 1 )
  & DSLTriggers.get_OwnerIsActor
  & NOT DSLTriggers.CurrentAbilityIs( AbilityOrEffect(<this+0x10> = TriggeredAbility 1319) )
  & DSLTriggers.AmountIsEqual(
        DSLFormulas.TimesAttackMadeThisTurn( attacker = Owner@+0x30, rangeType = null ),
        <DSLFormulas+0x20> = Direct(1) )

QUATRE lectures qui ne se devinent pas :

  * **`On(0xb = UnitAbility)`, PAS `On(0xe = UnitPostAbility)` ni `On(0x26 = NormalAttack)`.**
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` publie, dans l'ordre,
    `0x2a` -> execution -> **`0xb` INCONDITIONNEL** -> `if (IsActiveAbility) 0xc` ->
    `AddFlagsAfterAbilityExecution` -> `0xe`. Le `0xb` est donc le SEUL des trois qui fire pour
    l'attaque NORMALE **et** pour un cast, sans aucun discriminant de kind -- exactement ce qu'exige
    << after performing his first attack >>, l'attaque normale de Kariyan comme son
    `1191 MartialInspiration` comptant toutes deux. Le port ne l'emettait PAS (`handler.py` :
    << aucun consommateur porte >>) ; #928 l'ajoute sur les DEUX voies (cf.
    `triggers/dispatch/ability.py::unit_ability_triggers`).
  * **`AmountIsEqual(..., 1)`, pas `AmountIsGreaterThanZero`** : le gate est une EGALITE STRICTE a
    UNE attaque. C'est ce qui borne le passif a **une fois par tour** sans marqueur d'effet : la
    2e attaque du tour voit deja un compteur >= 2. `<DSLFormulas+0x20>` est le noeud constant
    `Direct(1)` pre-alloue par `IdunBattleLogic.Entities.DSLFormulas$$.ctor` (`+0x18 = Direct(0)`,
    `+0x20 = Direct(1)`, `+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`).
  * **`rangeType = null`** (3e argument de `DSLFormulas$$TimesAttackMadeThisTurn`, signature LUE) ->
    `IdunBattle.Entities.Formulas.AmountOfAttacksMadeThisTurnFormula$$Calculate` lit le compteur
    TOTAL `ActorStatisticsComponent+0x24`, PORTE depuis #508-r1
    (`components.unit_attacks_made_this_turn`). Les variantes Melee/Ranged (`+0x2c`/`+0x28`) ne sont
    pas alimentees ; ce call-site n'en a pas besoin. Le residu `#508-r2` citait `LegacyOfCombat`
    comme consommateur potentiel d'une variante : **il ne l'est pas** -- relu au decompile, le
    `Nullable` est VIDE.
  * **`NOT CurrentAbilityIs(<self>)`** : l'argument n'est PAS un litteral mais le champ `this+0x10`
    (le `TriggeredAbilityType` de l'instance), converti par la surcharge d'`AbilityOrEffect$$
    op_Implicit` qui appelle **`set_TriggeredAbility`** (adresse de `call` resolue -- les trois
    surcharges sont homonymes, cf. `martial_inspiration.py`). C'est une ANTI-RECURSION.

## 2. `...LegacyOfCombatAbility$$CreateBehaviour(abilityState, triggerType)`

    bigTargets = DSLSelectors.UnitsWithTrait(
                     DSLSelectors.AdjacentEnemies(Owner@+0x30, unique = 1, selectionType = 3),
                     0x3f9 = UnitTrait.BigTarget, selectionType = 3 )
    minMax2    = BaseTriggeredAbility.MinMaxDamage2(abilityState)          # minDmg_2 / maxDmg_2
    hits2      = DSLFormulas.Get( GetHits2() = GetNumberConstant(0x32 = nrOfHits_2) )
    profile2   = DSLSelectors.Direct( Nullable(GetDamageProfileOrDefault2(-1)
                                               = config.GetDamageProfile2()) )
    firstBT    = DSLSelectors.First(
                     DSLSelectors.SortTargetsByDamagePredictionSelector(
                         attacker = Owner@+0x30, units = DSLSelectors.Randomize(bigTargets),
                         ability  = DSLSelectors.Direct(AbilityOrEffect(1319)),
                         damage   = minMax2, hits = hits2, damageProfileType = profile2,
                         attackerSelectionType = 3 ),
                     amount = 1, ignoreForcedTargets = 0 )

    adjacents  = DSLSelectors.AdjacentEnemies(Owner@+0x30, unique = 1, selectionType = 3)
    minMax1    = BaseTriggeredAbility.MinMaxDamage(abilityState)           # minDmg / maxDmg
    profile1   = DSLSelectors.Direct( Nullable(GetDamageProfileOrDefault(-1)
                                               = config.GetDamageProfile()) )
    hits1      = GetHits() = GetNumberConstant(0x2f = nrOfHits)            # System.Int32

    return DSLBehaviors.If(
        DSLTriggers.AmountIsGreaterThanZero( firstBT ),
        DSLBehaviors.AttackWithAttackDamage( caster = Owner@+0x30, target = firstBT,
                                             amount = minMax2, damageProfile = profile2,
                                             hits = hits2, abilityOrEffect = AbilityOrEffect(1319),
                                             options = <struct ZEROEE>, selectionType = 2 ),
        DSLBehaviors.AttackWithAttackDamage( caster = Owner@+0x30, target = adjacents,
                                             amount = minMax1, damageProfile = profile1,
                                             hits = hits1, abilityOrEffect = AbilityOrEffect(1319),
                                             options = <struct ZEROEE>, selectionType = 2 ))

### LES SURCHARGES, tranchees par l'ADRESSE du `call` puis par le TYPE DECLARE

`probe_928_legacy_of_combat.py --step 2` desassemble les deux `Create*` et rend l'adresse RESOLUE de
chaque appel ; `frida/methods.tsv` donne ensuite la signature de CETTE adresse :

  * les **deux** `AttackWithAttackDamage` du corps sont des surcharges **DIFFERENTES** (deux
    adresses distinctes sur cinq formes) -- `hits : IdunBattle.DSL.IAmountFormula` pour la branche
    BigTarget, `hits : System.Int32` pour la branche adjacents (celle-ci enveloppe elle-meme
    l'entier dans un `DirectAmountFormula`). Meme semantique, deux ecritures : le port passe
    `hits_key` dans les deux cas et n'a rien a distinguer -- mais lire l'une pour l'autre aurait
    fait recopier `nrOfHits` la ou le natif lit `nrOfHits_2`.
  * `AmountIsGreaterThanZero` -> la surcharge `amount : IdunBattle.DSL.ITargetsSelector`, donc
    **`Count(firstBT) > 0`** (le corps fait `min = Direct(0) ; return min < amount`). La surcharge
    FORMULE, homonyme au bit pres, aurait lu un montant. Le port DISCRIMINE a l'evaluation.
  * `AdjacentEnemies` -> la variante `(unit, unique, selectionType)` (`Enemies(unit,
    Units(AdjacentTiles(unit), unique, selType) - unit, selType)`), et NON la variante
    `(unit, unitTile, unique)` qui code `3` en dur et dont le 3e argument est une ENTITE.
  * `First` -> `(entities, amount : System.Int32, ignoreForcedTargets)` : le `1` est un **NOMBRE
    D'ELEMENTS**, pas un index. `First(sel, amount = 1)` == `First(sel, index = 0)` cote port.

### CE QUE LE DECOMPILE DIT ET QUE L'i2 NE DIT PAS

  * **`Randomize` + tri par PREDICTION DE DEGAT sur les Big Targets.** L'i2 dit << an enemy Big
    Target >> comme s'il n'y en avait qu'un. Le natif, lui, PERMUTE aleatoirement les candidats
    (`PickRandomAmountSelector(amount = 0x7fffffff)` = permutation complete, `len(pool)` tirages
    `genrand_int32`) puis les trie par `SortTargetsByDamagePredictionSelector` (priorite aux KILLS :
    `int.MaxValue` si `WillBeKill`, `int.MaxValue - 1` si `MightBeKill`, sinon degat moyen predit) et
    ne garde que le premier. Le `Randomize` n'est donc PAS decoratif : c'est le TIE-BREAK entre deux
    Big Targets de meme prediction, et il CONSOMME du RNG.
  * **`selectionType = 3` (`OnlyAliveAndTargetable`) sur les DEUX selecteurs d'adjacence**, la ou le
    `selectionType` des deux `AttackWithAttackDamage` vaut `2` (`OnlyTargetable`).
  * **La branche << else >> frappe CHAQUE ennemi adjacent** (`AdjacentEnemies` est passe TEL QUEL en
    `target` : `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` resout la liste, l'`OrderBy`
    puis attaque chacun) -- mesure live #509 : 6 coups sur 2 cibles apres un cast de 1191.
  * **Aucun filtre d'equipe supplementaire, aucun cap, aucun marqueur d'effet.** Le bornage
    << une fois par tour >> vient ENTIEREMENT du `AmountIsEqual(TimesAttackMadeThisTurn, 1)`.

## 3. CE QUI FERME LE RESIDU #509-r1

`MartialInspiration_ExtraDamageEffect` (1408) porte
`ForPercentIncrease( OwnerIsCaster & (CurrentAbilityIs(1191) | CurrentAbilityIs(**1319**)), ... )`.
La 2e branche etait STRUCTURELLEMENT inatteignable cote port faute de porteur du canal. Les deux
feuilles ci-dessous passent `ability_type = 1319`, ce qui alimente `att_ctx["ability_type"]`
(`damage_model.attacker_modifiers`) : l'attaque supplementaire beneficie donc du buff de
`MartialInspiration` pose au meme tour, comme le natif.

## 4. RESIDUS NOMMES

  * `selectionType = 2` (9e argument d'`AttackWithAttackDamage`) : aucun etage de
    `UnitSelectionType` n'est materialise sur cette feuille -- residu PARTAGE par tous ses
    call-sites.
  * `options` (8e argument) : struct ZEROEE au call-site (5 qwords a 0, lus a l'assembleur) ->
    ni `isForceOverkill`, ni `forceCrit`, ni `skipHitsModifiers`. C'est exactement le defaut de la
    feuille portee.
  * **DOUBLE EVALUATION du sous-arbre `firstBT`** : le natif l'evalue une fois dans
    `AmountIsGreaterAbilityTrigger$$ShouldTrigger` (la condition du `If`) puis une SECONDE fois dans
    `AttackBehaviour$$Execute` (la cible), sans `Cache` intermediaire. Comme `Randomize` consomme
    `len(pool)` tirages, un pool de N Big Targets adjacents coute **2N** tirages, pas N. Le port
    reproduit la structure (deux evaluations du MEME noeud), donc la meme consommation.
    NON CONFRONTE live : aucun montage de cette tranche n'a mis >= 2 Big Targets adjacents a
    Kariyan (a N = 1 le tirage existe mais son resultat est force).
  * L'adjacence des selecteurs passe par `_within(..., order="adjacent")`, sans le gate d'elevation
    `|delta| < 2` d'`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$
    MoveNext` -- meme residu que tout le reste de la famille (#271).

## 5. Frontiere DSL/imperatif (#149)

Artefact natif = `CreateTrigger` + `CreateBehaviour` -> le `CreateTrigger` est COLLAPSE
imperativement dans `matches` (idiome de tous les trigger-ports), le `CreateBehaviour` est un VRAI
arbre DSL (`If` + deux feuilles `AttackWithAttackDamage`), la frontiere restant le `.execute` des
feuilles. AUCUN ciblage n'est recable a la main : les deux selecteurs EMERGENT des noeuds.

## 6. La face DECISION

  * MOUVEMENT : `playbook/legacy_of_combat.py` (`LegacyOfCombatPlaybook`, corps natif PROPRE).
  * ATTAQUE : `...LegacyOfCombatPlaybook.<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` a
    pour corps ENTIER `yield return Fix64.op_Implicit(0)` -> **DEAD**, donc absente de
    `TRIGGERED_ATTACK_PLAYBOOKS`. Verdict grave par `test_928_legacy_of_combat_offline.py`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.behaviours import If
from .....entities.damage_profile_type import DamageProfileType
from .....entities.selectors.accessors import Owner
from .....entities.selectors.geometry import Randomize
from .....entities.selectors.units import AdjacentEnemies, First, UnitsWithTrait
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggers import AmountIsGreaterThanZero
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.base import ability_attack_params
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....components import unit_attacks_made_this_turn
from ....state import State
from ...damage_prediction_sort import SortTargetsByDamagePrediction
from ..base import TriggeredAbility, TriggerEvent

#: cle gameconfig -- la config que `MinMaxDamage`/`GetHits`/`GetDamageProfile` resolvent.
ABILITY_ID = "LegacyOfCombat"
LEGACY_OF_COMBAT = int(TriggeredAbilityType.LegacyOfCombat)            # 0x527 = 1319
BIG_TARGET = int(UnitTrait.BigTarget)                                  # 0x3f9 = 1017

#: `On(0xb = UnitAbility, ownerNeedsToBeAlive = 1)` -- cf. SS 1.
_ON_UNIT_ABILITY = int(EventTriggerType.UnitAbility)                   # 0xb = 11
#: `<DSLFormulas+0x20>` = `Direct(1)` -- le 2e operande de l'`AmountIsEqual`.
_ATTACKS_MADE_TRIGGER_COUNT = 1
#: `selectionType = 3` des DEUX selecteurs d'adjacence (`UnitSelectionType.OnlyAliveAndTargetable`).
_SELECTION_ALIVE_AND_TARGETABLE = 3

#: volet 1 (branche << else >>, chaque ennemi adjacent) : `GetDamageProfile()` / `nrOfHits` /
#: `minDmg`,`maxDmg`. Les trois sont LUS au decompile, pas deduits du nom de l'ability.
PROFILE_ADJACENT = DamageProfileType.Power.name                        # config `damageProfile`
MIN_KEY_ADJACENT = AbilityVariableType.minDmg.name                     # `GetVariableForLevel(0xc)`
MAX_KEY_ADJACENT = AbilityVariableType.maxDmg.name                     # `GetVariableForLevel(0xd)`
HITS_KEY_ADJACENT = AbilityConstantType.nrOfHits.name                  # `GetNumberConstant(0x2f)`
#: volet 2 (branche BigTarget) : `GetDamageProfile2()` / `nrOfHits_2` / `minDmg_2`,`maxDmg_2`.
PROFILE_BIG_TARGET = DamageProfileType.Piercing.name                   # config `damageProfile_2`
MIN_KEY_BIG_TARGET = AbilityVariableType.minDmg_2.name                 # `GetVariableForLevel(0x36)`
MAX_KEY_BIG_TARGET = AbilityVariableType.maxDmg_2.name                 # `GetVariableForLevel(0x37)`
HITS_KEY_BIG_TARGET = AbilityConstantType.nrOfHits_2.name              # `GetNumberConstant(0x32)`


def adjacent_enemies_selector():
    """`DSLSelectors.AdjacentEnemies(Owner@+0x30, unique = 1, selectionType = 3)`.

    Foyer UNIQUE : le decompile construit DEUX instances de ce meme noeud (une pour la source des
    Big Targets, une pour la cible de la branche << else >>), avec des arguments IDENTIQUES --
    l'ecrire deux fois cote port serait un fork de la meme lecture. La surcharge est celle a
    `(unit, unique, selectionType)`, tranchee par l'adresse du `call` (cf. l'en-tete SS 2)."""
    return AdjacentEnemies(Owner(), selection_type=_SELECTION_ALIVE_AND_TARGETABLE)


def big_target_selector(state: State, owner_id: int):
    """`First(SortTargetsByDamagePredictionSelector(Randomize(UnitsWithTrait(AdjacentEnemies,
    BigTarget))), amount = 1)` -- MIRROR 1:1 de l'enchainement de quatre selecteurs.

    Les scalaires de degat/coups/profil passes au tri sont ceux du **volet 2** (`minDmg_2` /
    `maxDmg_2` / `nrOfHits_2` / `damageProfile_2`), c'est-a-dire exactement les noeuds
    `MinMaxDamage2` / `Get(GetHits2())` / `Direct(GetDamageProfileOrDefault2(-1))` que le natif
    passe au ctor : le selecteur trie par la prediction de **l'attaque qu'il prepare**, pas par une
    attaque generique. `level_slot="passive"` (`LegacyOfCombat` est un PASSIF, donc la config est
    resolue au niveau des passives)."""
    bmin, bmax, pierce, hits = ability_attack_params(
        state, owner_id, ABILITY_ID, PROFILE_BIG_TARGET, ranged=False,
        min_key=MIN_KEY_BIG_TARGET, max_key=MAX_KEY_BIG_TARGET, hits_key=HITS_KEY_BIG_TARGET,
        level_slot="passive")
    # `ctx.has_trait(unit, traitId)` (`abilities/behaviours/context.py`) resout `UnitTrait(int(...))`
    # -> le noeud attend l'ORDINAL, jamais le nom (un nom y leverait `ValueError` et rendrait FAUX
    # en silence). Le MEMBRE est ecrit ici, l'ordinal en est derive.
    big = UnitsWithTrait(adjacent_enemies_selector(), int(UnitTrait.BigTarget),
                         selection_type=_SELECTION_ALIVE_AND_TARGETABLE)
    ranked = SortTargetsByDamagePrediction(
        state=state, attacker=Owner(), targets=Randomize(big),
        # `ability = Direct(AbilityOrEffect(1319))` -- l'ability sous laquelle la prediction est
        # calculee, donc celle qui porte les bonus gates `CurrentAbilityIs`.
        ability_type=LEGACY_OF_COMBAT,
        damage_min=bmin, damage_max=bmax, hits=hits,
        damage_profile=PROFILE_BIG_TARGET, pierce=pierce, is_melee=True)
    # `First(..., amount = 1)` : le natif prend UN element (nombre, pas index). `index = 0` du
    # noeud porte rend exactement le premier -- meme resultat, cf. l'en-tete SS 2.
    return First(ranked)


def legacy_of_combat_tree(state: State, owner_id: int):
    """Arbre de `LegacyOfCombatAbility$$CreateBehaviour` -- MIRROR 1:1 :

        If( AmountIsGreaterThanZero(firstBigTarget),
            AttackWithAttackDamage(Owner, firstBigTarget, minDmg_2/maxDmg_2, Piercing, nrOfHits_2),
            AttackWithAttackDamage(Owner, AdjacentEnemies,  minDmg/maxDmg,   Power,    nrOfHits) )

    `multi=True` sur les DEUX feuilles : le natif passe un SELECTEUR en `target` et
    `AttackBehaviour$$Execute` resout la liste, l'`OrderBy` puis attaque CHAQUE cible -- il n'y a
    aucun collapse mono-cible ici (la branche BigTarget n'en a qu'une par construction du `First`,
    mais c'est le `First` qui la borne, pas la feuille).

    `ability_type=1319` = l'`abilityOrEffect` du call-site : c'est lui qui rend atteignable la 2e
    branche du gate de `MartialInspiration_ExtraDamage` (cf. l'en-tete SS 3)."""
    first_bt = big_target_selector(state, owner_id)
    return If(
        AmountIsGreaterThanZero(first_bt),
        AttackWithAttackDamage(first_bt, ABILITY_ID, PROFILE_BIG_TARGET, is_melee=True,
                               min_key=MIN_KEY_BIG_TARGET, max_key=MAX_KEY_BIG_TARGET,
                               hits_key=HITS_KEY_BIG_TARGET, multi=True, level_slot="passive",
                               ability_type=LEGACY_OF_COMBAT),
        AttackWithAttackDamage(adjacent_enemies_selector(), ABILITY_ID, PROFILE_ADJACENT,
                               is_melee=True, min_key=MIN_KEY_ADJACENT, max_key=MAX_KEY_ADJACENT,
                               hits_key=HITS_KEY_ADJACENT, multi=True, level_slot="passive",
                               ability_type=LEGACY_OF_COMBAT))


class LegacyOfCombatAdditionalAttackAbility(TriggeredAbility):
    """`On(0xb = UnitAbility) & OwnerIsActor & !CurrentAbilityIs(1319)
    & AmountIsEqual(TimesAttackMadeThisTurn(Owner, null), 1)`
    -> `If(AmountIsGreaterThanZero(<le Big Target le mieux classe>), 1x Piercing sur lui,
    3x Power sur CHAQUE ennemi adjacent)`.

    Lisible : la PREMIERE attaque du tour de Kariyan (attaque normale OU cast) en declenche une
    seconde, gratuite, resolue immediatement dans le meme appel. Cf. l'en-tete du module."""

    event_id = _ON_UNIT_ABILITY                       # `On(0xb, ownerNeedsToBeAlive = 1)`
    TRIGGERED_ABILITY_ID = LEGACY_OF_COMBAT           # `CurrentAbility` pose par `BaseTriggeredAbility$$Execute`

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """COLLAPSE du `CreateTrigger`. L'ordre suit celui du decompile ; le gate << owner vivant >>
        (`ownerNeedsToBeAlive = 1`) est deja applique par le dispatch."""
        actor = ev.actor_id
        if actor is None:
            return False
        # `get_OwnerIsActor` = `AreEqual(Owner@+0x30, Actor@+0x40)`. Sur ce vecteur l'ACTEUR est le
        # caster de l'ability qui vient de s'executer (`ActiveAbilityOperation` construit son
        # `AbilityEntities` avec caster == actor).
        if int(actor) != int(self.owner_id):
            return False
        # `NOT CurrentAbilityIs(AbilityOrEffect(TriggeredAbility 1319))` -- ANTI-RECURSION.
        # `ev.ability_type` porte `AbilityEntities.CurrentAbility` (`+0x60`), le champ que lit
        # `DSLTriggers$$CurrentAbilityIs` (meme canal que `FuelledByFury`/`PhoenixGem`).
        # ⚠ STRUCTURELLEMENT toujours VRAI sur les emetteurs portes : les deux voies de `0xb`
        # renseignent un `ActiveAbilityType` (ou le marqueur 1013 d'attaque normale), jamais un
        # `TriggeredAbilityType`, et le natif compare un `AbilityOrEffect` COMPLET (le discriminant
        # Active/Triggered/Effect en fait partie). Le terme est porte parce qu'il est ECRIT, pas
        # parce qu'il mord -- et il mordrait si un jour un vecteur `0xb` etait publie sous
        # `CurrentAbility = 1319`.
        if ev.ability_type is not None and int(ev.ability_type) == LEGACY_OF_COMBAT:
            return False
        # `AmountIsEqual( TimesAttackMadeThisTurn(Owner@+0x30, rangeType = null), Direct(1) )`
        # -> compteur TOTAL `ActorStatisticsComponent+0x24` (#508-r1), remis a zero au turn-start du
        # proprietaire. EGALITE STRICTE : c'est le bornage << une fois par tour >>.
        return (int(unit_attacks_made_this_turn(state, int(self.owner_id)) or 0)
                == _ATTACKS_MADE_TRIGGER_COUNT)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        owner_id = int(self.owner_id)
        # `AbilityEntities` du behaviour : caster == owner (le natif passe `Owner@+0x30` en `caster`
        # des DEUX `AttackWithAttackDamage`) ; l'`actor` reflete l'evenement, comme cote natif.
        entities = entities_from_state(state, owner_id, None, actor_id=ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        legacy_of_combat_tree(state, owner_id).execute(entities, ectx)
        atks = [p for (n, p) in ectx.emitted if n == "AttackWithAttackDamage"]
        if not atks:
            return None
        return {"passive": ABILITY_ID, "caster": owner_id,
                "targets": [p.get("target") for p in atks],
                "attacks": [p.get("attack") for p in atks],
                "total": sum(int(p.get("total") or 0) for p in atks), "dsl": True}
