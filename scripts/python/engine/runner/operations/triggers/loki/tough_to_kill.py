"""`ToughToKill_HealAbility` -- volet REGEN du passif `ToughToKill` (`TriggeredAbilityType` 0x5c5 =
**1477**) d'`astraDreir` (<< Dreir >>, HERO Astra Militarum, AU POOL).

i2 (autoritatif) : << At the beginning of his turn, Dreir **regenerates {[hpToHeal]} Health**. All
attacks against Dreir have -{[critChanceReduction]}% Crit Chance and deal -{[critDmgReduction]} Crit
Damage. >>

⚠ **LE PASSIF PORTE DEUX ABILITIES NATIVES.** La seconde phrase de l'i2 n'est PAS ce module : c'est
`ToughToKill_CritAbility` (: `AOwnerEffectTriggeredAbility`), qui pose l'owner-effect `ToughToKill`
(`EffectType` 0x5c0 = 1472) -- porte par `entities/effects/loki/tough_to_kill.py`. Les deux classes
sont voisines dans le bloc `methodPointers` du PE et derivent de bases DIFFERENTES (lues dans
`frida/classes.tsv`, jamais dans le nom du `.ctor`) :

    ToughToKill_HealAbility : IdunBattle.Entities.Abilities.BaseTriggeredAbility        <- CE module
    ToughToKill_CritAbility : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility

## LES DEUX ARBRES (build `rnca9r7q6c`)

- `$$CreateTrigger` -- corps FONDU par l'ICF (aucun symbole propre : il partage son adresse avec
  `IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility$$CreateTrigger`), donc LU
  par le bloc `methodPointers`, pas par un grep de nom :

      On(0x13 = 19 = TurnStart_Other, ownerNeedsToBeAlive: 1)  &  <DSLTriggers+0x28>

  `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` -- le champ que `IdunBattleLogic.Entities.DSLTriggers$$
  InitializeShared` construit a partir du selecteur `Owner@DSLSelectors+0x30` et de l'etat. MEME
  slot que `CursedPlagueBellMovementAbility` et `LivingMetalRepairAbility` : la regen ne fire QU'AU
  debut du tour du PROPRIETAIRE (mesure `probe_203` sur le slot jumeau : delta 0 au tour adverse).

- `$$CreateBehaviour` :

      Heal( healer   = Owner@DSLSelectors+0x30,
            selector = Owner@DSLSelectors+0x30,          <- le MEME registre, lu deux fois
            amount   = DSLFormulas.Get( AbilityConfiguration.GetVariableForLevel(
                           config@this+0x20, 0x20 = hpToHeal, abilityState, fallback: 0) ),
            options  = IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForRegenerate(
                           AbilityOrEffect(this.Id)) )

  `AbilityVariableType 0x20 = 32 = hpToHeal` (`enums.tsv`), DANS
  `variablesAffectedByRarityBonus` -> le multiplicateur de rarete mord. Le selecteur de cible est
  `Owner` DIRECT (PAS un `HealableUnits(...)`) : aucun pre-filtre `HealableUnitsSelector` n'est donc
  porte ici, exactement comme `TimeFluxAbility`.

  ⚠ `ForRegenerate` -> `(scope 1, remove_effects False)`, LU aux xrefs. `ToughToKill_HealAbility`
  etait explicitement NOMME comme l'un des trois call-sites `ForRegenerate` NON PORTES du build
  (docstring de `runner/abilities/behaviours/stats.py::Heal`) : il l'est desormais. `scope == 1`
  arme l'etage cap-de-GROUPE de `predict_heal` ; le porteur `astraDreir` est mono-membre, donc
  l'ecart mesure est NUL sur lui -- ce qui est declare ici est la FABRIQUE, pas un effet.

  ⚠ AUCUN noeud `IsDamaged(self)` (contraste `LivingMetalRepairAbility`) : le natif appelle le heal
  a PV pleins aussi, et c'est `HealUnitOperation` qui plafonne a `hp_max` (heal = 0). Ajouter la
  garde changerait le nombre d'events emis.

DOCTRINE #149 : le `CreateTrigger` est COLLAPSE dans `matches()` ; le `CreateBehaviour` est un VRAI
arbre DSL (feuille `Heal`, qui appelle l'Operation imperative `HealUnitOperation`).

ASCII only.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effects.magnitude import ability_var
from .....entities.selectors.accessors import Owner
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.stats import Heal
from ....components import OwnerComponent, StatsComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: Nom gameconfig du passif -- la CONFIG que `GetVariableForLevel(config@this+0x20, ...)` indexe.
ABILITY_ID = "ToughToKill"
#: `AbilityVariableType 0x20 = 32` (`enums.tsv`), DANS `variablesAffectedByRarityBonus`.
HP_TO_HEAL_KEY = "hpToHeal"
#: `IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForRegenerate` = `(scope 1, removeEffects 0)`.
REGENERATE_SCOPE = 1
REGENERATE_REMOVE_EFFECTS = False


def _passive_scaling(state: State, owner_id: int) -> tuple:
    """`(passive_ability_level, ability_variables_multiplier)` du porteur -- `ToughToKill` est un
    PASSIF, donc le niveau des `GetVariableForLevel` est `passive_ability_level`, jamais l'actif."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0, 100
    return (int(getattr(ctx, "passive_ability_level", 0) or 0),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def tough_to_kill_hp_to_heal(state: State, owner_id: int) -> int:
    """`GetVariableForLevel(config, 0x20 = hpToHeal, abilityState, 0)` (rarity-scale). 0 si absent --
    c'est litteralement le `fallback: 0` que le natif passe en 4e argument."""
    lvl, mult = _passive_scaling(state, owner_id)
    return int(ability_var(ABILITY_ID, HP_TO_HEAL_KEY, lvl, multiplier_pct=mult) or 0)


def tough_to_kill_regen_tree(hp_to_heal: int):
    """Arbre de `...ToughToKill_HealAbility$$CreateBehaviour` -- MIRROR 1:1 :

        Heal( Owner, Get(hpToHeal), options = ForRegenerate )

    Le `Direct`/`Get(GetVariableForLevel(...))` est FOLDE en scalaire (la magnitude est resolue par
    le natif AU MOMENT DE CONSTRUIRE le behaviour, pas a l'execution : `GetVariableForLevel` est
    appelee dans `CreateBehaviour` lui-meme). Pas de `guard` : le selecteur natif est `Owner`
    DIRECT, il n'y a AUCUN pre-filtre `HealableUnitsSelector` a mirrorer."""
    return Heal(Owner(), int(hp_to_heal),
                scope=REGENERATE_SCOPE, remove_effects=REGENERATE_REMOVE_EFFECTS)


class ToughToKillHealAbility(TriggeredAbility):
    """Volet REGEN -- `On(TurnStart_Other = 0x13 = 19, ownerNeedsToBeAlive: 1) & IsTurnOf(Owner)`
    -> `Heal(Owner, hpToHeal)`. Cf. l'en-tete de module pour les arbres natifs."""
    event_id = int(EventTriggerType.TurnStart_Other)        # On(0x13 = 19)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` : la regen ne fire qu'au debut du tour du
        # PROPRIETAIRE. `ownerNeedsToBeAlive: 1` est deja tenu par le dispatch (il ne visite que les
        # porteurs vivants) -- meme lecture que `LivingMetalRepairAbility`.
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        oc = e.get_component(OwnerComponent)
        return oc is not None and ev.player_id is not None and oc.player == int(ev.player_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        hp_to_heal = tough_to_kill_hp_to_heal(state, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        tough_to_kill_regen_tree(hp_to_heal).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        heals = [p for n, p in ectx.emitted if n == "Heal"]
        if not heals:
            return None
        amount = int(heals[0].get("amount") or 0)
        healed = sum(int(h.get("healed") or 0) for h in (heals[0].get("heals") or []))
        if amount <= 0:
            return None                    # `Heal` no-ope a montant <= 0 (mirror du natif)
        return {"type": "tough_to_kill_regen", "unit": int(self.owner_id),
                "hp_to_heal": hp_to_heal, "amount": amount, "healed": healed}
