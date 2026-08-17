"""`CursedPlagueBellMovementAbility` -- le volet MOUVEMENT du passif `CursedPlagueBell` (1071) de
`deathBlightbringer` / Corrodius (Death Guard, POOL-HERO rank 17).

i2 : « Friendly Chaos units STARTING THEIR TURN within Corrodius' Contagion aura gain +1 Movement
for this turn. » -- ce module porte la POSE (le trigger + l'arbre de cibles + l'`AddEffect`) ;
l'EFFET pose (`CursedPlagueBell_ExtraMove` 0x431=1073, `...$$AddStatModifier` = le +1 Movement) est
une tranche SEPAREE, non portee ici.

NB PLACEMENT : `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellMovementAbility` est
dans le namespace `Abilities.Active.Loki` mais derive de `IdunBattle.Entities.Abilities.
BaseTriggeredAbility` (releve `classes.tsv` du build : parent direct, et `BaseTriggeredAbility`
derive de `System.Object`, PAS d'`AActiveAbility`) -- exactement comme `DestroyerHiveAbility`,
`FireOfAbsolution`, `ControlEdict`. C'est donc un PASSIF TRIGGERED : il entre au registre
`ABILITY_TRIGGERS` (cle = `units.passiveAbilities` = `CursedPlagueBell`), PAS dans
`handler.ABILITY_CLASSES` (reserve aux ACTIVES).
=> Corollaire : NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` ne s'appliquent. Ces deux donnees
sont celles que `AActiveAbility$$.ctor` recoit (`TargetingOptions$$.ctor` + 3e argument
`AbilityAttackType`) ; `BaseTriggeredAbility$$Init(abilityConfigId, dsl, query, state, config,
operationProcessor, effectsDatabase, logger)` n'en prend AUCUNE, et la classe n'a ni `.ctor` propre
ni champ de ciblage. Les deux regles de non-regression du CLAUDE.md portent sur `ABILITY_CLASSES` :
elles sont SANS OBJET ici, et `probe_120` / `probe_181` le verifient (aucune entree ajoutee).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- TROIS fonctions natives NOMMEES
================================================================================================

## 1. `...CursedPlagueBellMovementAbility$$CreateTrigger`

    On(TurnStart_Other = 0x13 = 19, 1) & <DSLTriggers+0x28 = OwnerIsActor>

Le CORPS est PARTAGE (dedup IL2CPP de corps identiques) avec
`IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility$$CreateTrigger`, qui en est
le PROPRIETAIRE dans les tables indexees par adresse. Deux elements l'etablissent, aucun n'est une
deduction depuis l'absence :
  * le BLOC de classe est contigu dans `ghidra/functions.tsv` -- `CursedPlagueBellMovementAbility
    $$CreateBehaviour`, puis le corps attribue a `RelentlessMarchAbility$$CreateTrigger`, puis
    `CursedPlagueBellMovementAbility$$GetTargetsSelector` : la place du `CreateTrigger` de CETTE
    classe, dans SON bloc ;
  * `BaseTriggeredAbility$$GetTrigger` appelle le slot de vtable `+0x2d8` (`CreateTrigger`) et la
    base n'a AUCUN corps propre (abstraite) -> la classe DOIT en avoir un.
`<DSLTriggers+0x28>` = le meme slot que `...LivingMetalRepairAbility$$CreateTrigger` (`+0x28 &
On(0x13,1) & IsDamaged(Owner)`), que le port nomme `OwnerIsActor` et qui est PROUVE LIVE (#203,
probe_203 : la regen ne fire QU'AU tour du proprietaire). Porte = `ev.player_id ==
OwnerComponent.player`. Vecteur = `turn_start_other_triggers` (dispatch/turn.py).

## 2. `...CursedPlagueBellMovementAbility$$GetTargetsSelector(dsl, isDangerZone)`

    range   = DSLFormulas.ContagionsOfNurgleRange(unit = Owner,
                                                  unitSelectionType = 0 = Any,
                                                  isNextTurn = isDangerZone)
    targets = UnitsWithoutTrait(
                UnitsWithTrait(
                  SurroundingFriends(unit = Owner, range = range, unique = true,
                                     unitSelectionType = 3 = OnlyAliveAndTargetable),
                  trait = 0x7ea = UnitTrait.Chaos,      selectionType = 3),
                trait = 0x418 = UnitTrait.Stationary,   selectionType = 3)

`Owner` = `DSLSelectors+0x30`, le meme slot que `LivingMetalRepairAbility` passe a `IsDamaged` et
que `RelentlessMarchAbility` passe a `AdjacentUnits`/`Friends`.

`DSLSelectors$$SurroundingFriends(unit, range:IAmountFormula, unique, selType)` se DEPLIE en
    `Friends( of = unit,
              Units( SurroundingTiles(unit, includeCenter=1, range) - Tiles(unit), unique, selType ),
              selType )`
-> disque hex de rayon `range` autour de l'Owner, **centre EXCLU** (la soustraction `- Tiles(unit)`),
filtre ALLIES de l'Owner.

## 3. `...CursedPlagueBellMovementAbility$$CreateBehaviour(abilityState, triggerType)`

    AddEffect( effectType   = 0x431 = 1073 = EffectType.CursedPlagueBell_ExtraMove,
               abilityState = BaseTriggeredAbility.get_AbilityStateReference(this),
               targets      = <l'arbre du 2., avec isNextTurn = false>,
               turns        = Nullable<int>(1) )

C'est l'overload `DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns:Nullable<Int32>)`
(4 parametres) : la duree est deja en TOURS -> `duration_turns=1`, JAMAIS `TurnsFromRounds`.
Le behaviour ne lit PAS `triggerType` (aucune branche, contrairement a `RelentlessMarchAbility`).

## 4. `DSLFormulas$$ContagionsOfNurgleRange(unit, unitSelectionType, isNextTurn)`

    = new IdunBattle.Entities.Triggers.AuraEffectRangeFormula(
            effects, unit, effectType = 0x42f = EffectType.ContagionsOfNurgle_ArmorReduction1,
            unitSelectionType, isNextTurn)

et `AuraEffectRangeFormula$$Calculate(entities)` :
    unit = <selecteur `unit`>.Select(entities)
    if (unit == null) return 0
    def = effectsDatabase.Get(0x42f)                       // IAuraEffect
    if (!UnitExtensions.HasTrait(unit, def.GetTrait())) return 0
    entities.<slot Owner> = unit                           // re-ancrage
    return (isNextTurn ? def.GetNextTurnRange() : def.GetCurrentRange()).Calculate(entities)

L'implementation `IAuraEffect` est `IdunBattle.Entities.Effects.Loki.
ContagionsOfNurgle_ArmorReduction_Effect` :
    `$$GetTrait`          = `return 0x7eb` (= `UnitTrait.ContagionsOfNurgle`, 2027) -- LITTERAL ;
    `$$GetCurrentRange`   = `GetRangeOnOwnerTurn( StatAmount(Owner, 0xc=TurnsStarted, part 0) )` ;
    `$$GetNextTurnRange`  = `GetRangeOnOwnerTurn( Sum(StatAmount(Owner, 0xc, 0), Direct(1)) )` ;
    `$$GetRangeOnOwnerTurn(n)` = la table 1 / 2 / 3 aux seuils 2 et 4
        (foyer partage du port : `runner/abilities/deathguard.contagions_of_nurgle_range_for_turns`).

⚠ QUALIFICATION D'ENUM -- `0x42f` vaut 1071 dans DEUX enums distincts et les deux apparaissent
dans ce cas : `TriggeredAbilityType.CursedPlagueBell` (l'id du PASSIF) et
`EffectType.ContagionsOfNurgle_ArmorReduction1` (celui que lit `ContagionsOfNurgleRange`).
Ici c'est l'EffectType.

================================================================================================
FORME DU PORT
================================================================================================
DOCTRINE #149 : l'artefact natif est un `CreateBehaviour`/`GetTargetsSelector` -> ARBRE DSL. Les
predicats du `CreateTrigger` (`On` + `OwnerIsActor`) sont collapses imperativement dans `matches`
(comme LivingMetal / DestroyerHive) ; l'arbre, lui, est construit de noeuds EXISTANTS
(`SurroundingFriends`, `UnitsWithTrait`, `UnitsWithoutTrait`, feuille `AddEffect`) -- aucun
recablage a la main du ciblage.

SUBSTRAT DES TROIS GATES DE TRAIT (`Chaos`, `Stationary`, et le `ContagionsOfNurgle` de la formule
d'aura) : tous passent par `ctx.has_trait`, donc par `UnitContext.traits`, que `load_state` seede
depuis `combatSnapshot.units[].traits` depuis #264/#270 -- l'ensemble EFFECTIF invoque de
`IdunBattle.Entities.UnitExtensions$$HasTrait`, et non plus une reconstruction depuis le kit
gameconfig. C'est la MEME source que celle qu'interroge le natif ; les traits d'ALLIANCE (`Chaos`)
comme ceux poses EN BATAILLE (`Stationary` d'un summon `Movement = 0`) y sont.

RESIDUS EXPLICITES :
 * `unitSelectionType = 3 = OnlyAliveAndTargetable` : le port n'honore que le volet ALIVE
   (`_within` filtre les cadavres). Le volet TARGETABLE (`UnitBecameUntargetable` / deep-strike en
   cours d'atterrissage) n'est materialise nulle part cote port -> une unite VIVANTE mais
   non-ciblable serait comptee. Meme residu que tous les selecteurs d'occupation du port.
 * `unique = true` : `_within` ne peut pas produire de doublon (une unite = une position), le flag
   est donc sans effet observable ici.
 * `SurroundingFriends` du port prend `ctx.caster` comme reference de camp, la ou le natif prend
   son parametre `unit` (= Owner). Pour un triggered, `entities_from_state(state, owner_id, ...)`
   pose `caster = owner` -> IDENTIQUE. (Note assumee, pas une equivalence supposee : la construction
   du contexte est juste au-dessus, dans `execute_behaviour`.)
 * `isNextTurn = true` (la branche DANGER ZONE de `GetTargetsSelector`) n'est PAS portee : elle
   n'a aucun appelant ici (`CreateBehaviour` passe `false`). Le noeud leve si on la demande, plutot
   que de rendre un rayon faux en silence.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import AAmountFormula, TargetsSelector, resolve_unit
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.damage_profile_type import DamageProfileType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Actor
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import SurroundingFriends, UnitsWithTrait, UnitsWithoutTrait
from .....entities.stats import StatType
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....components import OwnerComponent, StatsComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Get
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.deathguard import contagions_of_nurgle_range_for_turns
from ....abilities.deathguard import cursed_plague_bell_damage_profile
from ....abilities.deathguard import is_in_contagions_of_nurgle_range

ABILITY_ID = "CursedPlagueBell"
EXTRA_MOVE = int(EffectType.CursedPlagueBell_ExtraMove)          # 0x431 = 1073
EXTRA_MOVE_NAME = "CursedPlagueBell_ExtraMove"
# `AuraEffectRangeFormula..ctor(effects, unit, effectType, ...)` : le 3e argument LITTERAL de
# `DSLFormulas$$ContagionsOfNurgleRange`. EffectType (PAS TriggeredAbilityType) -- cf. l'en-tete.
AURA_EFFECT = int(EffectType.ContagionsOfNurgle_ArmorReduction1)  # 0x42f = 1071
# `IAuraEffect.GetTrait()` PAR effect-def -- le natif l'interroge sur l'effet resolu par
# `effectsDatabase.Get(effectType)`, il n'est PAS cable en dur dans la formule. Seule entree lue :
# `ContagionsOfNurgle_ArmorReduction_Effect$$GetTrait` = `return 0x7eb` (litteral decompile).
# Un effect-def absent de cette table = `IAuraEffect` non porte -> la formule le dit, cf. `calculate`.
AURA_TRAIT_BY_EFFECT = {AURA_EFFECT: int(UnitTrait.ContagionsOfNurgle)}   # 0x42f -> 0x7eb = 2027
CHAOS = int(UnitTrait.Chaos)                                      # 0x7ea = 2026
STATIONARY = int(UnitTrait.Stationary)                            # 0x418 = 1048
PSYKER = int(UnitTrait.Psyker)                                    # 0x3ea = 1002
# Duree du `AddEffect` : `Nullable<int>(1)` -- deja en TOURS (overload 4-args de `DSLBehaviors.AddEffect`).
EXTRA_MOVE_TURNS = 1
# LITTERAL du conjoint `CurrentAttackDamageProfilesContain(0xd)` du `CreateTrigger` de la face ATTAQUE.
# ⚠ C'est une SECONDE source, distincte de la constante `affectedDamageProfile` que lit
# `GetDamageProfile` pour le profil de la riposte : le decompile ecrit un littéral ici et un
# `GetValueOrDefault` la-bas. Les deux coincident au gameconfig courant ; on ne les fusionne PAS.
ATTACK_GATE_PROFILE = DamageProfileType.Psychic.name                 # "Psychic"
VAR_DMG = "dmg"                     # `GetVariableForLevel(cfg, 0xb)` -- AbilityVariableType.dmg
CONST_NR_OF_HITS = "nrOfHits"       # `GetNumberConstant(cfg, 0x2f)` -- AbilityConstantType.nrOfHits


class ContagionsOfNurgleRange(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$ContagionsOfNurgleRange(unit, unitSelectionType,
    isNextTurn)` -> `IdunBattle.Entities.Triggers.AuraEffectRangeFormula$$Calculate` -- MIRROR (cf.
    en-tete de module, section 4) :

        u = unit.Select(entities) ; if (u == null) return 0
        if (!HasTrait(u, IAuraEffect(0x42f).GetTrait() = 0x7eb ContagionsOfNurgle)) return 0
        return GetCurrentRange().Calculate(entities re-ancre sur u)
             = GetRangeOnOwnerTurn( StatAmount(u, 0xc=TurnsStarted, Current) )

    Le re-ancrage natif (`entities.<slot Owner> = unit` avant l'evaluation du sous-formule) rend le
    `StatAmount(Owner, ...)` de `GetCurrentRange` equivalent a « le TurnsStarted de `u` » : c'est ce
    que le port lit directement, via `ctx.get_stat` (le meme accesseur que le noeud `StatAmount`).

    `effect_type` est le 3e argument du ctor natif (l'effet d'AURA interroge, PAS l'ability) ;
    `unit_selection_type` est CONSERVE tel quel (le natif le stocke @+0x1c et le passe au
    `Select` du selecteur) : il vaut 0 = Any sur l'unique call-site porte, et le selecteur `Caster()`
    du port ne discrimine pas -> aucun effet observable, mais l'argument reste NOMME plutot
    qu'efface. `is_next_turn=True` = la branche `GetNextTurnRange` (DangerZone) : NON PORTEE."""

    def __init__(self, unit: TargetsSelector, unit_selection_type: int = 0,
                 is_next_turn: bool = False, effect_type: int = AURA_EFFECT):
        self.unit = unit
        self.unit_selection_type = int(unit_selection_type)
        self.is_next_turn = bool(is_next_turn)
        self.effect_type = int(effect_type)

    def calculate(self, ctx):
        if self.is_next_turn:                       # `GetNextTurnRange` (Sum(TurnsStarted, 1)) -- residu
            raise NotImplementedError(
                "ContagionsOfNurgleRange(is_next_turn=True) : branche DangerZone non portee "
                "(`ContagionsOfNurgle_ArmorReduction_Effect$$GetNextTurnRange`)")
        # `def = effectsDatabase.Get(effectType)` : sans `IAuraEffect` porte pour ce type, le port
        # n'a PAS de `GetTrait()` a interroger -- il le DIT (jamais un 0 muet qui passerait pour
        # « l'unite n'a pas le trait »).
        trait = AURA_TRAIT_BY_EFFECT.get(self.effect_type)
        if trait is None:
            raise NotImplementedError(
                "AuraEffectRangeFormula : aucun IAuraEffect porte pour l'effectType %d "
                "(GetTrait/GetCurrentRange a lire au decompile)" % self.effect_type)
        u = resolve_unit(self.unit, ctx)
        if u is None:                               # `if (unit == null) return 0`
            return 0
        ht = ctx.has_trait or (lambda unit, tr: False)
        if not ht(u, trait):                        # `HasTrait(unit, IAuraEffect.GetTrait())`
            return 0
        gs = ctx.get_stat
        turns = 0 if gs is None else int(gs(u, int(StatType.TURNS_STARTED), 0, None) or 0)
        return contagions_of_nurgle_range_for_turns(turns)


def cursed_plague_bell_targets_selector(is_danger_zone: bool = False) -> TargetsSelector:
    """`...CursedPlagueBellMovementAbility$$GetTargetsSelector(dsl, isDangerZone)` -- MIRROR 1:1 :
    les ALLIES de l'Owner, dans le disque de son aura Contagion (centre EXCLU), qui portent le trait
    `Chaos` et ne portent PAS le trait `Stationary`.

    `Caster()` = le slot `DSLSelectors+0x30` (Owner) : pour un triggered, `entities_from_state`
    pose Owner == Caster (cf. residus de l'en-tete)."""
    owner = Caster()
    rng = ContagionsOfNurgleRange(owner, unit_selection_type=0, is_next_turn=is_danger_zone)
    friends = SurroundingFriends(owner, rng)        # `SurroundingFriends(Owner, range, unique, 3)`
    return UnitsWithoutTrait(UnitsWithTrait(friends, CHAOS), STATIONARY)


def cursed_plague_bell_movement_tree() -> AddEffect:
    """`...CursedPlagueBellMovementAbility$$CreateBehaviour` -- MIRROR 1:1 :
        `AddEffect(0x431 CursedPlagueBell_ExtraMove, AbilityStateReference,
                   GetTargetsSelector(dsl, false), turns = Nullable<int>(1))`.
    `duration_turns=1` (l'overload natif prend des TOURS, pas des rounds -> aucun
    `ConvertRoundsToTurns`) ; `source` = `AbilityStateReference` = le caster = l'Owner (defaut de la
    feuille du port)."""
    return AddEffect(EXTRA_MOVE, EXTRA_MOVE_NAME, cursed_plague_bell_targets_selector(),
                     duration_rounds=None, duration_turns=EXTRA_MOVE_TURNS)


class CursedPlagueBellMovementAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellMovementAbility` (volet
    MOUVEMENT du passif `CursedPlagueBell` 1071, `deathBlightbringer`) -- cf. en-tete de module.

    `On(TurnStart_Other=19) & OwnerIsActor` -> `AddEffect(CursedPlagueBell_ExtraMove 1073, 1 tour)`
    sur les allies Chaos non-Stationary du disque d'aura Contagion de l'Owner (centre exclu)."""
    event_id = int(EventTriggerType.TurnStart_Other)         # On(0x13 = 19)
    # `BaseTriggeredAbility$$Execute` ecrit `AbilityOrEffect(this.Id)` avant le behaviour -> c'est
    # ce que lit `TriggeringAbilityIs`. Id = `TriggeredAbilityType.CursedPlagueBell` (0x42f = 1071),
    # celui du PASSIF (les trois classes Attack/Movement/DangerZone le partagent).
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.CursedPlagueBell)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` = `On(0x13) & OwnerIsActor` -- et RIEN d'autre (aucun
        `AmountIsGreaterThanZero`, contrairement a DestroyerHive) : l'arbre de cibles VIDE est un
        no-op du behaviour, pas un gate du trigger."""
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        oc = e.get_component(OwnerComponent)
        # OwnerIsActor (`DSLTriggers+0x28`) : fire au debut du tour du PROPRIETAIRE uniquement.
        return oc is not None and ev.player_id is not None and oc.player == int(ev.player_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None                              # pas d'EffectsState -> pose impossible
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `entities_from_state(state, owner)` : Owner == Caster pour un triggered (le natif lit les
        # deux dans le meme slot `DSLSelectors+0x30` cote selecteurs). Pas de cible d'evenement.
        cursed_plague_bell_movement_tree().execute(
            entities_from_state(state, self.owner_id, None), ectx)
        placed = [p for n, p in ectx.emitted if n == "AddEffect"]
        if not placed:
            return None
        return {"type": "cursed_plague_bell_extra_move", "owner": int(self.owner_id),
                "targets": [p.get("target") for p in placed],
                "newly_placed": [p.get("target") for p in placed if p.get("placed")],
                "turns": EXTRA_MOVE_TURNS, "effect": EXTRA_MOVE}


# =====================================================================================================
# VOLET ATTAQUE (case-224 item 5) -- `CursedPlagueBellAttackAbility`
# =====================================================================================================
# i2 : « Enemy PSYKER units within Corrodius' Contagion aura deal {nrOfHits}x {dmg} Psychic Damage
#        TO THEMSELVES each time one of their attacks deals Psychic Damage. »
#
# ## `...CursedPlagueBellAttackAbility$$CreateTrigger` (decompile, ordre de lecture)
#
#     On(9 = EventTriggerType.Attack, ownerNeedsToBeAlive = 0)
#   & ( OwnerIsTarget | OwnerIsAlive<DSLTriggers+0x20> )
#   & NOT CasterIsTarget
#   & CurrentAttackDamageProfilesContain(0xd = Psychic, includeNotApplied = 0)
#   & AreEnemies(Actor@0x40, Owner@0x30, UnitTeamSelectionType = 0 = ByCurrentTeam)
#   & HasTrait(Actor@0x40, 0x3ea = UnitTrait.Psyker)
#   & IsInContagionsOfNurgleRange                 # = IsInUnitContagionsOfNurgleAura(Actor, Owner)
#   & NOT CurrentAbilityIs(this)
#
# `<DSLTriggers+0x20>` est NOMME par lecture, pas par mesure :
# `IdunBattleLogic.Entities.DSLTriggers$$On(triggerType, ownerNeedsToBeAlive)` choisit LITTERALEMENT
# le slot `+0x20` quand le drapeau est vrai et le slot `+0x70` (trigger neutre) sinon -- `+0x20` est
# donc le conjoint « OWNER VIVANT ». Recoupement independant : `DSLTriggers$$InitializeShared`
# construit `+0x20` avec le seul `state` (ce dont
# `IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger$$ShouldTrigger` a besoin :
# `IsUnit(owner) ? UnitExtensions.IsAlive(owner, state) : true`) et `+0x70` SANS argument.
#
# ## `...CursedPlagueBellAttackAbility$$CreateBehaviour(abilityState, triggerType)`
#
#     DSLBehaviors.AttackWithAttackDamage(
#         caster          = Actor@0x40,                       # le PSYKER -- il s'attaque LUI-MEME
#         target          = Actor@0x40,                       # le MEME slot, lu deux fois
#         amount          = DSLFormulas.Get( GetVariableForLevel(cfg, 0xb = dmg, abilityState) ),
#         damageProfile   = Nullable<DamageProfileType>( GetAffectedDamageProfile()
#                                                        .GetValueOrDefault(0xd = Psychic) ),
#         hits            = GetNumberConstant(cfg, 0x2f = nrOfHits),
#         abilityOrEffect = (AbilityOrEffect)this,
#         options         = default(Nullable<AttackDamageBehaviourOptions>),   # 0x28 octets a ZERO
#         selectionType   = 2 = UnitSelectionType.OnlyTargetable )
#
# OVERLOAD identifie par SA SIGNATURE dans `frida/methods.tsv` (`damageProfile:Nullable<
# DamageProfileType>`, `hits:System.Int32`) -- cinq overloads d'`AttackWithAttackDamage` coexistent, et
# ils different justement sur ces deux parametres. `DSLFormulas$$Get(int)` = le noeud constante
# (`Direct`), donc le montant est FIGE a la construction de l'arbre, avec l'`abilityState` du PORTEUR.
# `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` batit
# `AttackDamageBehaviour(state, Caster@0x48, Target@0x60, amount, profile, Direct(hits), ...)` puis
# `AttackBehaviour(caster, target, <ce behaviour>, abilityOrEffect)` : les deux selecteurs passes
# (ici `Actor` deux fois) sont ceux de l'AttackBehaviour EXTERNE, qui re-ancre le contexte.
#
# FORME DU PORT (doctrine #149) : `CreateBehaviour` -> ARBRE DSL (feuille `AttackWithAttackDamage`
# existante, mode `amount`) ; les conjoints du `CreateTrigger` -> collapse imperatif dans `matches`,
# SAUF `IsInContagionsOfNurgleRange` qui est deja un NOEUD DSL porte (case-224 item 4,
# `runner/abilities/deathguard.is_in_contagions_of_nurgle_range`) et dont ce port est le PREMIER
# consommateur moteur.
#
# `options` VIDE (`HasValue = 0`, les 0x28 octets sont mis a zero juste avant l'appel) => aucune
# variance d'arme sur le montant => `amount_spread_pct = 0` (meme regime que le smite Psyker), et ni
# `alwaysOverkilled` ni `alwaysCrit`.
#
# CHAINE VERIFIEE (#449-r2) : `GetValueOrDefault` dans
# `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor` depose les 0x28 octets a `+0x98`, donc
# l'octet d'aiguillage (options+6) est `behaviour+0x9e` -> `$$ExecuteTarget` (options+0x2f) ->
# `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (request+0x6a) ->
# `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`, ou `0` prend la branche PLATE
# `MinMaxDamageFix64(d, d)` et non-zero prend `$$GetBaseDamageFix64` (+-20 %).
# ⚠ Le byte est le MEME qu'en #449, mais sa conclusion ne se transporte PAS : cote PREDICTION il vaut
# `1` EN DUR (les trois surcharges de `DamagePredictionQuery$$GetAttackPrediction`), cote COMBAT c'est
# l'ability qui l'ecrit -- `SkyStrikeAbility$$ExecuteBehaviour` le pose a 1 (`uStack_1e2 = 1`).
# MESURE live (case-449-r2 §4) : forcer 20 ici fait diverger le recul de 99 et 593 points.


def cursed_plague_bell_attack_hits() -> int:
    """`AbilityConfiguration.GetNumberConstant(cfg, 0x2f = nrOfHits)` -- le 5e argument
    (`hits:System.Int32`) de l'overload d'`AttackWithAttackDamage` retenu. Constante d'ability, donc
    NON scalee par la rarete."""
    return int(ability_var(ABILITY_ID, CONST_NR_OF_HITS, is_constant=True) or 1)


def cursed_plague_bell_attack_damage(state: State, owner_id: int) -> int:
    """`AbilityConfiguration.GetVariableForLevel(cfg, 0xb = dmg, abilityState)` -- le montant que
    `DSLFormulas.Get(...)` fige dans le noeud constante de l'arbre.

    ⚠ Le niveau et le multiplicateur de rarete sont ceux du PORTEUR de la cloche (l'`abilityState` que
    `BaseTriggeredAbility` passe a `CreateBehaviour` est le sien), PAS ceux du psyker qui subit
    l'attaque -- alors meme que le CASTER de l'`AttackWithAttackDamage` est ce psyker. C'est
    exactement la dissociation que le decompile impose, et elle n'est pas devinable depuis la feuille
    (dont le `level_slot` lit toujours le caster) : d'ou le mode `amount` plutot que le mode bornes.
    `dmg` est dans `variablesAffectedByRarityBonus` -> le scaling `AbilityVariablesMultiplier`
    s'applique (mirror `ability_var`). Passif -> `passive_ability_level` (repli `active_ability_level`,
    meme regle qu'`ability_attack_params(level_slot="passive")`)."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    if ctx is None:
        level, mult = 0, 100
    else:
        level = (ctx.passive_ability_level if ctx.passive_ability_level is not None
                 else ctx.active_ability_level)
        mult = ctx.ability_variables_multiplier
    return int(ability_var(ABILITY_ID, VAR_DMG, level, multiplier_pct=mult) or 0)


def cursed_plague_bell_attack_tree(amount: int):
    """`...CursedPlagueBellAttackAbility$$CreateBehaviour` -- MIRROR 1:1 de l'unique feuille.

    `Actor()` porte les DEUX selecteurs natifs (`caster` ET `target` sont le meme slot `+0x40`) : le
    caster de l'attaque est fourni par l'`entities` construit dans `execute_behaviour` (ancre sur
    l'acteur), et la cible par ce selecteur. `is_melee=False` : `attackRangeType = "Ranged"` a la
    config d'ability. `native_factory="attack"` : la factory natif est bien `AttackWithAttackDamage`
    (et non `AttackWithAbilityDamage`) -- classification par le call-site, pas au juge.
    `amount_spread_pct=0` : le `Nullable<AttackDamageBehaviourOptions>` natif est passe VIDE.
    Import paresseux (cycle triggers <-> abilities.behaviours, == martial_superiority)."""
    return AttackWithAttackDamage(Actor(), ABILITY_ID, cursed_plague_bell_damage_profile(),
                                  is_melee=False, amount=Get(int(amount)),
                                  hits=cursed_plague_bell_attack_hits(),
                                  native_factory="attack", amount_spread_pct=0)


class CursedPlagueBellAttackAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility` (volet ATTAQUE du
    passif `CursedPlagueBell` 1071, `deathBlightbringer`) -- cf. le bloc RE juste au-dessus.

    Meme placement que la classe MOUVEMENT : parent direct `BaseTriggeredAbility` (`classes.tsv`),
    donc `ABILITY_TRIGGERS` et NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` (elles ne concernent que
    `ABILITY_CLASSES`, le registre des ACTIVES).

    ⚠ **`fire_on_death` = VRAI (#10015), ET C'EST CE QUI REND LA DISJONCTION `OwnerIsTarget |
    OwnerIsAlive` DE `matches` ATTEIGNABLE.** `IdunBattleLogic.Entities.Abilities.Active.Loki.
    CursedPlagueBellAttackAbility` surcharge `IdunBattle.Entities.Abilities.ITriggeredAbility`
    slot 8 = `get_AllowForDeadOwner` et son corps rend VRAI (`b0 01 c3`, LU --
    `metadata/allow_for_dead_owner.tsv`). Le port le laissait au defaut FAUX de
    `IdunBattle.Entities.Abilities.BaseTriggeredAbility` : `IdunBattle.Operations.
    EvaluateTriggerOperation$$CanGetAbilityTrigger` coupait alors AVANT `matches` sur tout porteur
    mort, si bien que le membre `OwnerIsTarget` -- ecrit plus bas et qui vise precisement le porteur
    FRAPPE -- n'avait plus aucun regime ou etre vrai sans que `OwnerIsAlive` le soit deja. La
    disjonction native etait degradee en son membre droit, en silence."""
    event_id = int(EventTriggerType.Attack)                  # On(9), ownerNeedsToBeAlive = 0
    #: `ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` -> VRAI (cf. la docstring).
    fire_on_death = True
    # Les trois classes du passif partagent l'id `TriggeredAbilityType.CursedPlagueBell` (0x42f=1071),
    # que `BaseTriggeredAbility$$Execute` ecrit avant le behaviour.
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.CursedPlagueBell)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        actor, target = ev.actor_id, ev.target_id
        if actor is None:
            return False
        # --- NOT CasterIsTarget (`AreEqual(Caster@0x48, Target@0x60)`) -------------------------------
        # Le port n'a pas de slot CASTER distinct sur un evenement d'attaque : `TriggerEvent` porte
        # `actor_id` (l'attaquant) et `target_id`. Sur les DEUX vecteurs `On(9)`
        # (`after_hit_normal_attack` / `after_hit_ability_attack`) l'acteur EST le caster du coup ->
        # collapse assume `Caster == Actor`. C'est aussi le gate qui BORNE la recursion : la riposte
        # est une AUTO-attaque (caster == target == le psyker), donc elle ne se re-declenche pas.
        if target is not None and int(target) == int(actor):
            return False
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        # --- ( OwnerIsTarget | OwnerIsAlive ) -------------------------------------------------------
        # `OwnerIsAliveAbilityTrigger$$ShouldTrigger` : `IsUnit(owner) ? IsAlive(owner, state) : true`.
        # ⚠ CE N'EST PLUS << vrai par construction >> : depuis #10015 la classe porte
        # `fire_on_death = True` (mirror LU de `get_AllowForDeadOwner`), donc `CanGetAbilityTrigger`
        # laisse passer un porteur MORT et c'est ici que la disjonction tranche pour de bon --
        # `OwnerIsTarget` devient le seul membre vrai quand le porteur vient d'etre tue par le coup.
        ouc = owner.get_component(UnitComponent)
        owner_is_alive = ouc is None or bool(ouc.alive)
        if not (owner_is_alive or (target is not None and int(target) == int(self.owner_id))):
            return False
        # --- CurrentAttackDamageProfilesContain(0xd = Psychic) --------------------------------------
        # `DamageProfilesContainsTrigger$$ShouldTrigger` = `<liste de profils de l'attaque>.Contains(
        # damageProfileType)` (liste nulle -> faux). `ev.profiles` = le SET COMPLET (arme + bonus-hits
        # #179) quand le vecteur le threade ; repli `{ev.profile}` sinon (voie ABILITY, cf. residus).
        profs = ev.profiles if ev.profiles else ({ev.profile} if ev.profile else set())
        if ATTACK_GATE_PROFILE not in profs:
            return False
        # --- AreEnemies(Actor@0x40, Owner@0x30) -----------------------------------------------------
        ae = state.get_entity(actor)
        if ae is None:
            return False
        aoc = ae.get_component(OwnerComponent)
        ooc = owner.get_component(OwnerComponent)
        if aoc is None or ooc is None or aoc.team == ooc.team:
            return False
        # --- HasTrait(Actor@0x40, 0x3ea = Psyker) ---------------------------------------------------
        asc = ae.get_component(StatsComponent)
        a_traits = set(getattr(asc.ctx, "traits", None) or ()) if asc is not None else set()
        if UnitTrait(PSYKER).name not in a_traits:
            return False
        # --- NOT CurrentAbilityIs(this) -------------------------------------------------------------
        # `IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs` compare le selecteur du slot
        # `DSLSelectors+0x88` (= `AbilityTypeSelector.CurrentAbilitySelector`, qui LIT
        # `AbilityEntities+0x60`) a `Direct(AbilityOrEffect(this))`.
        #
        # Le canal lu ici EST ce champ-la (case-292, RE relue et confrontee) :
        # `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` pose
        # `Nullable<AbilityOrEffect>(this.Id)` dans `+0x60` **AVANT** d'appeler le behaviour, et le
        # `.ctor` de copie d'`AbilityEntities` le propage a toute sous-construction
        # (`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` reconstruit un `AbilityEntities`
        # mais n'ecrase que Caster/Target : il HERITE `+0x60`). Le port pose `state.triggering_ability`
        # au meme moment (avant `execute_behaviour`) et le restaure apres -> meme champ, meme portee.
        # Le NOM du champ Python est historique : le champ natif `TriggeringAbility` (`+0x98`, slot
        # `DSLSelectors+0x90`) est ecrit APRES le behaviour, pour `On(0xd = UnitTriggeredAbility)` seul.
        #
        # `ability_type` reste EXCLU : ce canal-la est keye sur l'espace `ActiveAbilityType`, ou 1071
        # vaut `AnnihilatorBeam` -- y injecter le `TriggeredAbilityType` 1071 ferait lire une AUTRE
        # ability par tous les gates de kind (meme refus que `MartialSuperiority`/`MartialApotheosis`).
        #
        # REDONDANCE MESUREE : `NOT CasterIsTarget` ci-dessus mord deja sur la riposte (auto-attaque),
        # donc neutraliser CE gate seul ne change aucun observable du montage `probe_224` (mutation
        # `nogate`, 0 rouge). Ce qui est OBSERVABLE, c'est la RESTAURATION du canal : sans elle, le
        # second coup de cloche du smite `PsykerExtraAttack` (1013) disparait (mutation `persist`).
        if getattr(state, "triggering_ability", None) == self.TRIGGERED_ABILITY_ID:
            return False
        # --- IsInContagionsOfNurgleRange (NOEUD DSL, case-224 item 4) --------------------------------
        # `IsInUnitAura(Actor, 1071, Caster)` = `MinDistance(Actor, Owner) <= AuraEffectRange(Owner)`,
        # comparateur INCLUSIF (`AmountIsEqualOrGreaterAbilityTrigger`, #293 -- le nom du `.ctor` est
        # DEDUPLIQUE et ne designe pas la classe).
        # `entities_from_state(state, owner, actor_id=actor)` pose Caster == Owner
        # (regle des triggered) et l'acteur de l'evenement dans le slot `Actor`.
        ctx = entities_from_state(state, self.owner_id, None, int(actor))
        return bool(is_in_contagions_of_nurgle_range().should_trigger(ctx))

    def execute_behaviour(self, state: State, ev: TriggerEvent):
        actor = ev.actor_id
        if actor is None:
            return None
        amount = cursed_plague_bell_attack_damage(state, self.owner_id)
        # Le natif ancre l'`AttackBehaviour` sur `Actor` pour le caster ET pour la cible : le psyker
        # se frappe lui-meme. On construit donc l'`entities` avec `caster_id = actor_id` (c'est ce que
        # lit la feuille pour l'armure/percage/crit) et le meme id dans le slot `Actor` (ce que lit le
        # selecteur de cibles). Le porteur de la cloche n'intervient QUE par le montant (cf.
        # `cursed_plague_bell_attack_damage`).
        entities = entities_from_state(state, int(actor), None, int(actor))
        ectx = ExecutionContext(state=state, rng=state.rng)
        cursed_plague_bell_attack_tree(amount).execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        atk = atks[0] if atks else None
        if atk is None:
            return None
        return {"type": "cursed_plague_bell_attack", "owner": int(self.owner_id),
                "caster": int(actor), "target": atk.get("target"),
                "amount": int(amount), "total": atk.get("total"), "attack": atk.get("attack")}
