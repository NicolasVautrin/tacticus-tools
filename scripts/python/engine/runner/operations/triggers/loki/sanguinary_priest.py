"""`SanguinaryPriest` (`TriggeredAbilityType.SanguinaryPriest` = 1296) -- passif de kit de
`bloodSanguinary` << Nicodemus >> (HERO Blood Angels). RE : decompile ghidra, build `rnca9r7q6c`,
symboles CONFIRMES par `search_symbols_by_name` + `frida/methods.tsv` (les trois existent, aucun
n'est un fold ICF).

## Les TROIS artefacts natifs, lus verbatim

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SanguinaryPriestAbility$$CreateTrigger` :

    On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive = 1)
      op_BitwiseAnd  <DSLTriggers+0x28>            # = IsTurnOf(Owner)
      op_BitwiseAnd  get_OwnerIsActor

⚠ TROIS termes, la ou son voisin de forme `SpiritualLeaderAbility$$CreateTrigger` n'en a que DEUX
(`On(0x1c) & get_OwnerIsActor`). Le terme supplementaire `<DSLTriggers+0x28>` est ecrit par
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` (`ctor(<DSLSelectors+0x30> = Owner,
<dsl+0x10> = state)`) et vaut `IsTurnOf(Owner)` -- identification etablie par
`docs/rl/case-366-r1-turnof-all.md` §2, et partagee par les huit autres call-sites portes
(`heavy_warp_flamer`, `relentless_march`, `serene_unifier`, `terminator_armour`, ...). NE PAS
recopier la forme du voisin : le gate est ici, et il est LU.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SanguinaryPriestAbility$$GetTargets` :

    adj  = DSLSelectors.AdjacentFriends(Owner@DSLSelectors+0x30, unique = 1,
                                        selectionType = 3 = OnlyAliveAndTargetable)
    mech = DSLSelectors.MechanicalUnits(adj, 3)
    return adj op_Subtraction mech

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SanguinaryPriestAbility$$CreateBehaviour` :

    lo      = AbilityConfiguration.GetVariableForLevel(cfg, 0x20 = hpToHeal,    abilityState)
    hi      = AbilityConfiguration.GetVariableForLevel(cfg, 0x47 = maxHpToHeal, abilityState)
    targets = <le MEME sous-arbre que GetTargets, re-construit inline>
    amount  = DSLFormulas.RandomAmount(lo, hi)
    options = IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForRegenerate(
                  AbilityOrEffect(this.Id))
    return DSLBehaviors.Heal(healer = Owner@DSLSelectors+0x30, selector = targets,
                             amount = amount, options = options)

i2 : « After moving, Nicodemus restores `{hpToHeal}`-`{maxHpToHeal}` Health to all adjacent
non-mechanical allies. If Nicodemus does not move, then this ability triggers at the end of his
turn. » -- la seconde phrase est portee PAR L'EVENEMENT lui-meme (les deux emetteurs natifs de
`On(0x1c)`, cf. `dispatch/move_death.py::arrived_at_final_tile_triggers`), pas par une 2e branche.

## Les SURCHARGES, tranchees par les XREFS ENTRANTES (jamais par le pseudo-C)

* `RandomAmount` : le build en porte DEUX (`(min: Int32, max: Int32)` et
  `(min: IAmountFormula, max: IAmountFormula)`, meme nom au decompile). `CreateBehaviour` appelle
  la variante **Int32** -- etabli par `list_xrefs` sur les deux adresses, `SanguinaryPriestAbility$$
  CreateBehaviour` figure dans les appelants de la premiere et PAS de la seconde. Consequence de
  port : les deux bornes sont des CONSTANTES resolues avant l'arbre (`Const`), pas des `ConfigVar`
  paresseux -- meme regime que `champion_of_the_feast.armor_reduction`.
* `AdjacentFriends` : DEUX surcharges d'arite 4 aussi (`(unit, unique, selectionType)` /
  `(unit, unitTile, unique)`). Les xrefs designent la **UNIT-ancree** `(unit, unique,
  selectionType)` -- la meme que `BloodChaliceAbility$$GetTargets`, PAS la TILE-ancree
  qu'appelle `RitesOfRestorationAbility$$GetHealTargets`. Le `3` est donc un `UnitSelectionType`,
  jamais un rayon.

## Ce que le passif n'a PAS, et que son plus proche voisin a

`IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$GetTargets` -- l'ACTIF du MEME
porteur -- ajoute un troisieme etage : `UnitsWithoutTrait(adj - mech, 0x19 = UnitTrait.Immune, 3)`.
`SanguinaryPriestAbility$$GetTargets` s'arrete a la soustraction : **aucun filtre `Immune`**. Les
deux sous-arbres ont ete relus cote a cote pour cette tranche ; recopier le voisin aurait ajoute un
filtre que le natif n'ecrit pas.

## Le MONTANT est tire PAR CIBLE, et c'est mesure dans le natif

`IdunBattle.Entities.Behaviours.HealBehaviour$$Execute` appelle `<+0x60>.Calculate(entities)`
**DANS** la boucle d'enumeration des cibles (`get_Current` -> `Calculate` -> `processor.<slot 0x57>
(healer, target, amount, scope, removeEffects, source)`), exactement comme son jumeau
`RepairBehaviour$$Execute` que `operations/repair.py` cite depuis #299. Sur un `Direct(...)` cela
ne s'observe pas ; sur un `RandomAmount` **si** : deux allies adjacents recoivent DEUX tirages
INDEPENDANTS. La feuille `abilities/behaviours/stats.py::Heal` evaluait son `amount_fn` une seule
fois AVANT la boucle -- corrige dans le meme commit (cf. sa docstring), ce qui repare du meme coup
le tirage FANTOME que le port consommait quand le selecteur ne rend AUCUNE cible (le natif, lui,
n'entre jamais dans la boucle donc n'appelle jamais `Calculate`).

`RandomAmount$$Calculate` = `rng.NextInternal(min, max + 1)` (borne haute INCLUSIVE, cf.
`entities/formulas.py::RandomAmount`).

## Les options de soin

`HealBehaviourOptions$$ForRegenerate` = `(scope 1, removeEffects 0)` -- LU aux xrefs ; c'est l'une
des SIX fabriques `ForRegenerate` du build, et `SanguinaryPriestAbility` y est nommement citee par
la docstring de la feuille `Heal`. `scope = 1` arme le cap de GROUPE `GetGroupUnitHealLimit` dans
`DamagePrediction$$PredictHeal` ; `removeEffects = 0` = le soin ne purge PAS les effets negatifs
(contraste `ForHeal`, que l'effet 1368 `BloodChalice_HealOnAttack` du MEME porteur utilise, lui).

## Doctrine #149

Le `CreateTrigger` est COLLAPSE imperativement dans `matches()` (les trois termes sont des gates
d'evenement) ; le `CreateBehaviour` est un VRAI ARBRE DSL (`AdjacentFriends`/`MechanicalUnits`/`Sub`
+ formule `RandomAmount` + feuille `Heal`, qui appelle l'Operation `HealUnitOperation`). Aucun
filtre n'est recable a la main : le gate `AttackQuery$$EntityCanBeHealed` et
`DamagePrediction$$PredictHeal` vivent sous la feuille, dans `operations/heal.py` (#520).

## Face DECISION (hors de ce module)

`IdunBattle.AI.Playbook.SanguinaryPriestPlaybook` -- porte dans
`engine/playbook/adjacent_unit_preference.py` (meme commit) : utilite de MOUVEMENT
`Sum(amis adjacents affectes par le heal-type 0 -> +SanguinaryPriest_AdjacentNonMechanicalFriend,
et +SanguinaryPriest_AdjacentDamagedNonMechanicalFriend de plus si l'ami est BLESSE)`.
`CalculateAttackUtilityInStepsInternal` rend `Fix64(0)` : aucune utilite d'attaque.

ASCII only (console cp1252).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.formulas import RandomAmount
from .....entities.effects.magnitude import ability_var
from .....entities.selectors.accessors import Owner
from .....entities.selectors.units import AdjacentFriends, MechanicalUnits, Sub
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.stats import Heal
from ....components import OwnerComponent, StatsComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "SanguinaryPriest"
HP_TO_HEAL_KEY = "hpToHeal"                  # `AbilityVariableType.hpToHeal`    = 0x20 = 32
MAX_HP_TO_HEAL_KEY = "maxHpToHeal"           # `AbilityVariableType.maxHpToHeal` = 0x47 = 71

#: 3e argument LITTERAL des DEUX appels `DSLSelectors$$AdjacentFriends` / `MechanicalUnits`.
SELECTION_TYPE = int(UnitSelectionType.OnlyAliveAndTargetable)          # 3

#: `HealBehaviourOptions$$ForRegenerate` = `(scope 1, removeEffects 0)`.
HEAL_SCOPE = 1
HEAL_REMOVE_EFFECTS = False

_ON_ARRIVED = int(EventTriggerType.ArrivedAtFinalTile)                  # 0x1c = 28


def sanguinary_priest_targets():
    """`...SanguinaryPriestAbility$$GetTargets` -- MIRROR 1:1 :

        adj  = AdjacentFriends(Owner@DSLSelectors+0x30, unique = 1, selectionType = 3)
        mech = MechanicalUnits(adj, 3)
        return adj op_Subtraction mech

    Le natif passe la MEME instance d'`adj` aux deux etages (`pvVar4` est reutilise par
    `MechanicalUnits` puis par `op_Subtraction`) : on fait pareil -- le selecteur est PUR, donc
    l'evaluation serait identique avec deux instances, mais la structure citee l'est aussi.

    `MechanicalUnits` = `UnitExtensions$$IsMechanical` = `HasTrait(Mechanical=5) ||
    HasTrait(LivingMetal=1000) || HasTrait(Vehicle=1029)` -- TROIS traits (cf. `selectors/units.py`).
    ⚠ Le filtre est SUR LE SELECTEUR, donc plus strict que le gate `IsAffectedByHealType(u, 0)` de
    l'Operation : une unite qui porterait A LA FOIS `AffectedByHealAndRepair` et `Mechanical` passe
    le gate mais est ECARTEE ici. C'est ce que le natif ecrit.

    AUCUN filtre `UnitTrait.Immune` : c'est l'ACTIF `BloodChalice` du meme porteur qui en a un
    (`UnitsWithoutTrait(adj - mech, 0x19, 3)`), pas ce passif."""
    # `AdjacentFriends(unit, unique, selectionType)` : la surcharge UNIT-ancree (xrefs). Le port
    # exprime l'anneau-1 par `radius = Const(1)` (`AdjacentTiles` natif) et la reference d'equipe par
    # `Owner()` (le centre EST la reference dans cette surcharge).
    adj = AdjacentFriends(Owner(), Const(1), Owner(), selection_type=SELECTION_TYPE)
    return Sub(adj, MechanicalUnits(adj, SELECTION_TYPE))


def _passive_scaling(state: State, owner_id: int) -> tuple:
    """`(passive_ability_level, ability_variables_multiplier)` du porteur. `SanguinaryPriest` est un
    PASSIF -> le niveau des `GetVariableForLevel` est `passive_ability_level`, JAMAIS l'actif."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0, 100
    return (int(getattr(ctx, "passive_ability_level", 0) or 0),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def sanguinary_priest_hp_to_heal(state: State, owner_id: int) -> int:
    """`GetVariableForLevel(cfg, 0x20 = hpToHeal, abilityState)` -- borne BASSE du `RandomAmount`.
    `hpToHeal` figure dans `variablesAffectedByRarityBonus` -> le multiplier de rarete s'applique."""
    lvl, mult = _passive_scaling(state, owner_id)
    return int(ability_var(ABILITY_ID, HP_TO_HEAL_KEY, lvl, multiplier_pct=mult) or 0)


def sanguinary_priest_max_hp_to_heal(state: State, owner_id: int) -> int:
    """`GetVariableForLevel(cfg, 0x47 = maxHpToHeal, abilityState)` -- borne HAUTE (INCLUSIVE) du
    `RandomAmount`. Egalement dans `variablesAffectedByRarityBonus`."""
    lvl, mult = _passive_scaling(state, owner_id)
    return int(ability_var(ABILITY_ID, MAX_HP_TO_HEAL_KEY, lvl, multiplier_pct=mult) or 0)


def sanguinary_priest_behaviour_tree(lo: int, hi: int, rng=None):
    """`...SanguinaryPriestAbility$$CreateBehaviour` -- MIRROR 1:1 :

        Heal( healer  = Owner@DSLSelectors+0x30,
              targets = GetTargets(),
              amount  = RandomAmount(Direct(hpToHeal), Direct(maxHpToHeal)),
              options = HealBehaviourOptions.ForRegenerate(AbilityOrEffect(this.Id)) )

    Les deux `GetVariableForLevel` sont resolus AVANT l'arbre (surcharge Int32 de `RandomAmount`,
    tranchee aux xrefs) -> `Const`. Le `rng` est un CHAMP du noeud `RandomAmount` (pose par la
    factory depuis `DSLFactory+0x18`), pas une entree du contexte : on le passe au constructeur,
    comme le natif. `rng = None` -> le noeud rend sa borne MIN sans consommer de tirage (degradation
    documentee de `entities/formulas.py::RandomAmount`), ce qui rend l'arbre testable offline.

    L'`amount_fn` de la feuille est le `Calculate` du noeud : la feuille l'appelle **PAR CIBLE**,
    mirror de `HealBehaviour$$Execute` -> chaque allie adjacent tire SON montant."""
    amount = RandomAmount(Const(int(lo)), Const(int(hi)), rng=rng)
    return Heal(sanguinary_priest_targets(),
                lambda entities, ectx: int(amount.calculate(entities)),
                scope=HEAL_SCOPE, remove_effects=HEAL_REMOVE_EFFECTS)


class SanguinaryPriestAbility(TriggeredAbility):
    """`SanguinaryPriestAbility` (`TriggeredAbilityType` 0x510 = 1296, passif de `bloodSanguinary`).

    `On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive = 1) & IsTurnOf(Owner) & OwnerIsActor`
    -> `Heal(Owner, AdjacentFriends(Owner,1,3) - MechanicalUnits(.), RandomAmount(hpToHeal,
       maxHpToHeal), ForRegenerate)`.

    Cf. l'en-tete du module pour les trois arbres natifs, les surcharges tranchees aux xrefs et le
    tirage PAR CIBLE."""
    event_id = _ON_ARRIVED
    # `BaseTriggeredAbility$$Execute` ecrit `AbilityOrEffect(this.Id)` avant le behaviour -> c'est ce
    # que lit `TriggeringAbilityIs`.
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.SanguinaryPriest)    # 0x510 = 1296

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` COLLAPSE (doctrine #149), terme par terme :

          * `On(0x1c, ownerNeedsToBeAlive = 1)` : l'evenement est deja filtre par le dispatch ; le
            volet « owner vivant » (`<DSLTriggers+0x20>` = `OwnerIsAliveAbilityTrigger`) est ici ;
          * `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` = `OwnerComponent.player ==
            State.current_player_id` (mirror `UnitExtensions$$IsControlledByCurrentPlayer`, MEME
            foyer de lecture que `runner/components.py::is_turn_of_owner`). TRI-ETAT : proprietaire
            ou joueur courant NON MESURE -> la clause degrade en VRAI, jamais en FAUX invente
            (meme regle que le foyer) ;
          * `get_OwnerIsActor` = `AreEqual(<DSLSelectors+0x30>, <DSLSelectors+0x40>)` = l'unite qui
            vient de terminer son activation EST le porteur.

        ⚠ `IsTurnOf(Owner)` est en pratique implique par `OwnerIsActor` sur les DEUX emetteurs de
        `On(0x1c)` (une unite ne bouge / ne cloture son tour que pendant le tour de son camp) : il
        est porte parce que le natif l'ECRIT, pas parce qu'un regime porte le distingue. Aucun
        tirage PRNG n'est consomme par ce gate."""
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:                  # `ownerNeedsToBeAlive = 1`
            return False
        if ev.actor_id != self.owner_id:                     # `get_OwnerIsActor`
            return False
        oc = e.get_component(OwnerComponent)                 # `<DSLTriggers+0x28>` = IsTurnOf(Owner)
        cur = getattr(state, "current_player_id", None)
        owner_player = getattr(oc, "player", None) if oc is not None else None
        if owner_player is None or cur is None:
            return True                                      # non mesure -> on ne ferme PAS le gate
        return int(owner_player) == int(cur)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        lo = sanguinary_priest_hp_to_heal(state, self.owner_id)
        hi = sanguinary_priest_max_hp_to_heal(state, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `entities_from_state(state, owner)` : pour un triggered, Owner == Caster == le porteur
        # (`BaseTriggeredAbility$$Execute` execute le behaviour sur son propre porteur). `actor_id`
        # est threade pour rester homogene avec les autres consommateurs d'`On(0x1c)`.
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        sanguinary_priest_behaviour_tree(lo, hi, rng=state.rng).execute(entities, ectx)
        heals = next((p for n, p in ectx.emitted if n == "Heal"), None) or {}
        per_target = [{"target": h.get("target"), "healed": int(h.get("healed") or 0),
                       "amount": int(h.get("amount") or 0)}
                      for h in (heals.get("heals") or [])]
        if not per_target:
            return None
        return {"type": "sanguinary_priest_regen", "unit": int(self.owner_id),
                "hp_to_heal": lo, "max_hp_to_heal": hi, "heals": per_target,
                "healed": sum(h["healed"] for h in per_target)}
