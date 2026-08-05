"""`IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility` -- le passif
`RelentlessMarch` (`TriggeredAbilityType` 0x3ec = 1004) de `necroWarden` << Makhotep >> (Necrons,
HERO, dans le pool rank 17). #328, tranche 1 de l'inventaire `docs/rl/case-317-repair-callers-
inventory.md` (13 appelants de `IdunBattleLogic.Entities.DSLBehaviors$$Repair`).

i2 : « Gives +1 Movement to all friendly units that start their turn in an adjacent hex. Also
repairs affected Mechanical units for {hpToRepair} Health. »

⚠ QUALIFICATION D'ENUM -- 1004 vaut `TriggeredAbilityType.RelentlessMarch` ICI, et
`ActiveAbilityType.MortisRound` dans l'autre enum. Toute citation de 1004 dans ce module est un
`TriggeredAbilityType`.

NB PLACEMENT : la classe est dans le namespace `Abilities.Active.Loki` mais derive de
`IdunBattle.Entities.Abilities.BaseTriggeredAbility` (releve `data/symbols/<build>/frida/classes.tsv`,
taille 96), exactement comme `CursedPlagueBellMovementAbility`. C'est donc un PASSIF TRIGGERED : il
entre au registre `ABILITY_TRIGGERS` (cle = `units.passiveAbilities` = `RelentlessMarch`), PAS dans
`handler.ABILITY_CLASSES` (reserve aux ACTIVES).
=> Corollaire : NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` ne s'appliquent -- les deux regles de
non-regression du CLAUDE.md portent sur `ABILITY_CLASSES`, et `probe_181` / `probe_120` le verifient
(aucune entree ajoutee).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- les DEUX faces. Detail in extenso, disassemblage des
deux call-sites et reachability de la branche `Custom` : `docs/rl/case-328-relentless-march.md`.
================================================================================================

## 1. `...RelentlessMarchAbility$$CreateTrigger`

    IdunBattleLogic.Entities.DSLTriggers$$On(0x13 = TurnStart_Other, ownerNeedsToBeAlive = true)
      & <DSLTriggers+0x28>

L'overload d'`On` retenu est celui qui prend un **bool** (`On(type) & (alive ? this+0x20 :
this+0x70)`), identifie par l'ADRESSE du `call` -- les deux overloads homonymes ont la meme
signature affichee. Le volet « owner vivant » (`+0x20` = `OwnerIsAliveAbilityTrigger`) est deja le
gate `CanGet*Trigger` du dispatch porte, pas re-ecrit ici.

⚠ CORRECTION DE NOMMAGE (#328). `living_metal.py` et `cursed_plague_bell.py` appellent `<DSLTriggers
+0x28>` « OwnerIsActor ». Le slot et la propriete `get_OwnerIsActor` sont DEUX objets differents, et
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` les construit cote a cote :

    this+0x28        = new <DAT_1833ab568>( DSLSelectors+0x30 = Owner, dsl+0x10 = state, 0 )
    get_OwnerIsActor = new <DAT_1833a6968>( DSLSelectors+0x30 = Owner, DSLSelectors+0x40 = Actor, 0 )

Deux tokens de classe distincts, deux 2es arguments distincts. `DAT_1833ab568` est le token
qu'alloue **`IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)`** (unique instanciateur du
build) -> `+0x28` = `IsTurnOf(Owner)` -> `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger`, dont le
`$$ShouldTrigger` compare l'index de joueur de l'entite resolue a celui du contexte. C'est
exactement la semantique deja collapsee par le port (`ev.player_id == OwnerComponent.player`,
prouvee live par `probe_203`) : le COMPORTEMENT porte etait juste, seul le NOM etait emprunte.

## 2. `...RelentlessMarchAbility$$CreateBehaviour(abilityState, triggerType)`

    targets = DSLSelectors.Friends( of       = Owner@DSLSelectors+0x30,
                                    entities = DSLSelectors.AdjacentUnits(Owner, unique = 1,
                                                                          selectionType = 3),
                                    selectionType = 3 )

    v = AbilityConfiguration.GetVariableForLevel(config@this+0x20, 0x24 = hpToRepair, abilityState, 0)

    if (triggerType == 0x20 = EventTriggerType.Custom)
        targets = targets op_Subtraction DSLSelectors.HeroUnits(targets, 3)

    return  DSLBehaviors.AddEffect( effectType   = 0x3f3 = EffectType.RelentlessMarch_Effect,
                                    abilityState = BaseTriggeredAbility.get_AbilityStateReference(this),
                                    targets      = DSLSelectors.UnitsWithoutTrait(targets,
                                                             0x418 = UnitTrait.Stationary, 3),
                                    turns        = Nullable<int>(1) )
          op_Addition
            DSLBehaviors.Repair( mechanic = Owner@DSLSelectors+0x30,
                                 selector = targets,                    # <- SANS le filtre de trait
                                 amount   = DSLFormulas.Direct(v),
                                 source   = (AbilityOrEffect)(TriggeredAbilityType 0x3ec),
                                 options  = RepairBehaviourOptions.ForRepair() )   # (0, 1)

⚠⚠ **`UnitsWithoutTrait(Stationary)` filtre la cible de l'`AddEffect`, PAS celle du `Repair`** -- la
fiche #317 disait l'inverse. Lu au DESASSEMBLAGE des deux call-sites (`r14` = le resultat FILTRE part
en 4e argument d'`AddEffect` ; `rbx` = l'arbre NON filtre part en 3e argument de `Repair`).
Consequence de jeu, observable : **un allie adjacent `Stationary` ne recoit PAS le +1 Mouvement mais
il EST repare**. Recopier la fiche aurait refuse cette reparation -- degradation restrictive et
silencieuse.

  * `DSLSelectors$$AdjacentUnits(origin, unique, selType)` = `Units(AdjacentTiles(origin), unique,
    selType) op_Subtraction origin` -> l'Owner est EXCLU de sa propre selection, et ce selecteur ne
    filtre AUCUNE equipe (c'est le `Friends` au-dessus qui le fait, referent = l'Owner) ;
  * `DSLSelectors$$HeroUnits(src, selType)` DELEGUE litteralement a `UnitsWithTrait(src, 0x10 =
    UnitTrait.Hero, selType)` -- aucune classe dediee (d'ou le helper `hero_units` du port) ;
  * `IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRepair` relue sur ce build :
    `+0x10 = 0` (scope), `+0x14 = 1` (removeEffects) ;
  * l'overload d'`AddEffect` retenu est celui a 5 parametres `(effectType, abilityState, targets,
    turns:Nullable<Int32>)`, `source` passe a `0` par la fabrique -- identifie par l'ADRESSE du
    `call` (quatre overloads homonymes coexistent) : la duree est deja en TOURS, donc
    `duration_turns=1`, JAMAIS un `TurnsFromRounds` ;
  * `IdunBattle.Core.AbilityOrEffect$$op_Implicit` (l'overload retenu, idem par adresse) fait
    `set_TriggeredAbility(Nullable<TriggeredAbilityType>(v))` -> le litteral `0x3ec` est bien un
    `TriggeredAbilityType`.

## 3. BRANCHE `triggerType == Custom` -- REACHABILITY MESUREE

`Custom` n'arrive jamais par le trigger propre de l'ability (`On(TurnStart_Other)`). Le producteur du
littéral est unique et NOMME :

    IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility
        ... ITriggeredAbility.ExecuteBy(ability, &abilityState, entities, 0x20)   # 0x20 EN DUR

C'est le bout de chaine de `DSLBehaviors$$TriggerAbility` / `$$TriggerAbilityDelayed` = « une AUTRE
ability declenche EXPLICITEMENT cette triggered-ability ». Et le declencheur existe : c'est l'ACTIVE
DU MEME PORTEUR --
`IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$ExecuteBehaviour`
(`ActiveAbilityType` 1005, `necroWarden.activeAbilities`) contient

    If( DSLTriggers.ActorHasTriggeredAbility(ActiveTarget@DSLSelectors+0x48, 0x3ec),
        DSLBehaviors.TriggerAbility(ActiveTarget@0x48, 0x3ec, ..., selectionType = 3,
                                    ignoreUnitHavingAbility = 0) )

et son `$$GetNonCharacterFriendsSelector(units)` = `Friends(Owner, units) - HeroUnits(units)` -- LA
MEME soustraction que la branche `Custom`, ce qui en dit le sens : rejouee par `AdaptiveStrategy`,
`RelentlessMarch` ne beneficie qu'aux allies NON-Character.

RESIDU NOMME : la branche est PORTEE (mirror 1:1) mais n'a **aucun appelant cote port** --
`ActiveAbilityType` 1005 `AdaptiveStrategy` n'est pas dans `ABILITY_CLASSES`. Elle devient
confrontable live le jour ou `AdaptiveStrategyAbility` sera portee ; d'ici la elle est exercee par un
test OFFLINE (le parametre `trigger_type` ci-dessous), jamais rendue muette.

## 4. FORME DU PORT (doctrine #149)

`CreateBehaviour` -> ARBRE DSL : `Seq( AddEffect(UnitsWithoutTrait(targets, Stationary), turns=1),
Repair(targets, Direct(hpToRepair)) )`, construit de noeuds EXISTANTS (`AdjacentUnits`, `Friends`,
`UnitsWithoutTrait`, `hero_units`, `Sub`) -- aucun noeud neuf, aucun ciblage recable a la main. La
FRONTIERE est le `.Execute` des feuilles : `AddEffect` appelle `AddEffectOperation`, `Repair` appelle
`IdunBattle.Operations.RepairUnitOperation$$Execute` (#299) ; ni l'une ni l'autre n'en re-ecrit un
etage. Les predicats du `CreateTrigger` sont collapses imperativement dans `matches` (meme patron que
`LivingMetal` / `CursedPlagueBell`).

## 5. LE GATE `EntityCanBeRepaired` MORD -- deux fois, et le montage l'exerce

Contrairement a `LivingMetal` (gate TAUTOLOGIQUE : porter `LivingMetal` implique `IsMechanical`), la
cible n'est PAS le porteur :
  * `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(target, 1)` = `HasTrait(0x421
    AffectedByHealAndRepair) || IsMechanical(target)` -> un allie adjacent ORGANIQUE recoit le
    +1 Mouvement et RIEN en PV ;
  * `IsDamagedUnit(target)` -> un allie a PV pleins n'est pas repare ;
  * `!IsMachine(target)` -> une Machine of War adjacente n'est jamais reparee (et, `Stationary`, ne
    recoit pas non plus l'effet).

## 6. RESIDUS NOMMES (liste complete : case-328 section 8)

  * branche `Custom` sans appelant porte (section 3) ;
  * `RelentlessMarchDangerZoneAbility` (`$$GetEffectType` = `return 0x42c` = 1068
    `RelentlessMarch_DangerZone`, parent `AOwnerEffectTriggeredAbility`) et
    `RelentlessMarchDangerZoneEffect$$CreateRangeBonusForDangerZone` : axe PREDICTION de zone de
    danger, NON porte (meme choix que `CursedPlagueBellDangerZoneAbility`) ;
  * `IdunBattle.AI.Playbook.Loki.RelentlessMarchPlaybook` : face DECISION, hors perimetre ;
  * `unitSelectionType = 3` (`OnlyAliveAndTargetable`) : le port n'honore que le volet ALIVE ;
  * `unique = true` d'`AdjacentUnits` : sans effet observable (une unite = une position) ;
  * `source = AbilityOrEffect(RelentlessMarch)` du `Repair` : aucun observable d'etat porte ;
  * `necroWarden` porte AUSSI `LivingMetal`, dont le trigger part sur le MEME `On(TurnStart_Other)`.
    Les deux sont portes ; le montage de validation vise des cibles Mechanical NON-`LivingMetal` pour
    que le delta de PV soit imputable au seul `RelentlessMarch`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import TargetsSelector
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import Seq
from .....entities.effect_type import EffectType
from .....entities.selectors import (AdjacentUnits, Caster, Friends, Sub, UnitsWithoutTrait,
                                     hero_units)
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....components import OwnerComponent, StatsComponent
from ....state import State
from ....abilities.behaviours import AddEffect, Repair, entities_from_state
from ..base import TriggeredAbility, TriggerEvent
from .....entities.effects.magnitude import ability_var

ABILITY_ID = "RelentlessMarch"
# `AddEffect(effectType = 0x3f3, ...)` -- `EffectType`, PAS `TriggeredAbilityType`.
MARCH_EFFECT = int(EffectType.RelentlessMarch_Effect)        # 0x3f3 = 1011
MARCH_EFFECT_NAME = "RelentlessMarch_Effect"
# `turns = Nullable<int>(1)` de l'overload 5-args d'`AddEffect` : deja en TOURS.
MARCH_EFFECT_TURNS = 1
# `UnitsWithoutTrait(targets, 0x418, 3)` -- le filtre porte sur la cible de l'AddEffect SEULE.
STATIONARY = int(UnitTrait.Stationary)                       # 0x418 = 1048
HP_TO_REPAIR_KEY = "hpToRepair"          # `AbilityVariableType` 0x24 = 36 (cle gameconfig)
REPAIR_SCOPE = 0                         # `RepairBehaviourOptions$$ForRepair` : +0x10 = 0
REPAIR_REMOVE_EFFECTS = True             # ...                                  +0x14 = 1

_ON_TURN_START_OTHER = int(EventTriggerType.TurnStart_Other)  # `On(0x13 = 19)`
_CUSTOM = int(EventTriggerType.Custom)                        # 0x20 = 32 (branche, cf. section 3)


def relentless_march_targets(trigger_type: int = _ON_TURN_START_OTHER) -> TargetsSelector:
    """L'arbre de cibles COMMUN aux deux feuilles de `...$$CreateBehaviour` -- MIRROR 1:1 :

        Friends( of = Owner@0x30, AdjacentUnits(Owner, unique = 1, selType = 3), selType = 3 )
        [ op_Subtraction HeroUnits(<le meme arbre>, 3)   si triggerType == 0x20 = Custom ]

    `Caster()` = le slot `DSLSelectors+0x30` (Owner) : pour un triggered, `entities_from_state(state,
    owner_id, ...)` pose `caster == owner`. `AdjacentUnits` exclut deja l'origine (le natif fait
    `Units(AdjacentTiles(origin)) - origin`) et ne filtre AUCUNE equipe ; le camp vient du `Friends`
    au-dessus, dont le REFERENT est l'Owner (2e argument natif), pas une constante.

    La SOUSTRACTION reprend le MEME noeud `base` des deux cotes, comme le natif reprend le meme
    `pvVar2` -- l'arbre est donc evalue deux fois, exactement comme lui."""
    owner = Caster()
    base = Friends(AdjacentUnits(owner), owner)
    if int(trigger_type) == _CUSTOM:
        return Sub(base, hero_units(base))
    return base


def relentless_march_behaviour_tree(amount: int,
                                    trigger_type: int = _ON_TURN_START_OTHER) -> Seq:
    """`...$$CreateBehaviour` -- MIRROR 1:1 du `op_Addition` des DEUX feuilles :

        AddEffect(0x3f3 RelentlessMarch_Effect, AbilityStateReference,
                  UnitsWithoutTrait(targets, 0x418 Stationary), turns = Nullable<int>(1))
      + Repair(Owner, targets, Direct(hpToRepair), AbilityOrEffect(1004), ForRepair)

    ⚠ Le `UnitsWithoutTrait` n'enveloppe QUE la cible de l'`AddEffect` (cf. section 2 de l'en-tete) :
    le `Repair` recoit l'arbre NON filtre.

    `amount` est resolu par l'APPELANT parce que le natif le resout lui aussi AVANT de batir l'arbre
    (`GetVariableForLevel` puis `DSLFormulas$$Direct`) : c'est une CONSTANTE de l'arbre, pas un noeud
    paresseux -- meme forme que `FabricatorClawArray` et `DawnBlade`."""
    targets = relentless_march_targets(trigger_type)
    return Seq(AddEffect(MARCH_EFFECT, MARCH_EFFECT_NAME,
                         UnitsWithoutTrait(targets, STATIONARY),
                         duration_rounds=None, duration_turns=MARCH_EFFECT_TURNS),
               Repair(targets, amount,
                      scope=REPAIR_SCOPE, remove_effects=REPAIR_REMOVE_EFFECTS))


def hp_to_repair(state: State, owner_id: int) -> int:
    """`AbilityConfiguration$$GetVariableForLevel(config, 0x24 = hpToRepair, abilityState, 0)`.

    `hpToRepair` EST dans `variablesAffectedByRarityBonus` du gameconfig de `RelentlessMarch` -> le
    multiplicateur de rarete s'applique (`ability_var` gate l'application sur cette liste). PASSIF ->
    `passive_ability_level` (meme lecture que `FabricatorClawArray`, l'autre `hpToRepair` de passif).
    0 si l'unite / son contexte / la variable manquent -> la feuille `Repair` est alors un no-op
    (`amount > 0` est sa garde)."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    if ctx is None:
        return 0
    lvl = getattr(ctx, "passive_ability_level", None)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    return int(ability_var(ABILITY_ID, HP_TO_REPAIR_KEY, lvl, multiplier_pct=mult) or 0)


class RelentlessMarchAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility` -- passif
    `RelentlessMarch` (`TriggeredAbilityType` 0x3ec = 1004) de `necroWarden` << Makhotep >>.

    Au debut du tour de SON proprietaire : `+1 Mouvement` (effet 1011, 1 tour) aux allies adjacents
    NON-`Stationary`, et `hpToRepair[niveau]` PV a TOUS les allies adjacents -- les non-mecaniques
    etant ecartes par le gate `EntityCanBeRepaired` de l'Operation, pas par un selecteur.
    Cf. l'en-tete du module."""
    event_id = _ON_TURN_START_OTHER
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.RelentlessMarch)     # 0x3ec = 1004

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` moins le volet porte par le dispatch (`On(0x13)` + owner vivant) :
        il ne reste que `<DSLTriggers+0x28> = IsTurnOf(Owner)` (cf. section 1 de l'en-tete),
        collapse en « le proprietaire est le joueur dont le tour DEMARRE »."""
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        oc = e.get_component(OwnerComponent)
        return oc is not None and ev.player_id is not None and oc.player == int(ev.player_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        amount = hp_to_repair(state, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `entities_from_state(state, owner)` pose `caster = owner` : le natif lit l'Owner dans le
        # MEME slot `DSLSelectors+0x30` pour le referent du `Friends`, l'origine de l'`AdjacentUnits`
        # et le `mechanic` du `Repair`. Aucune cible d'evenement (`On(TurnStart_Other)` n'en porte pas).
        entities = entities_from_state(state, self.owner_id, None)
        # `triggerType` = l'event du dispatch. La branche `Custom` n'a aucun appelant cote port
        # (section 3) -- on passe donc l'event REEL, jamais une constante choisie.
        relentless_march_behaviour_tree(amount, ev.event_id).execute(entities, ectx)
        placed = [p for (n, p) in ectx.emitted if n == "AddEffect"]
        rep = next((p for (n, p) in ectx.emitted if n == "Repair"), {})
        repairs = rep.get("repairs") or []
        repaired = sum(int(r.get("repaired") or 0) for r in repairs)
        if not placed and repaired <= 0:
            return None
        return {"passive": ABILITY_ID, "owner": int(self.owner_id), "amount": int(amount),
                "effect": MARCH_EFFECT, "turns": MARCH_EFFECT_TURNS,
                "moved": [p.get("target") for p in placed],
                "newly_placed": [p.get("target") for p in placed if p.get("placed")],
                "repairs": repairs, "repaired": repaired}
