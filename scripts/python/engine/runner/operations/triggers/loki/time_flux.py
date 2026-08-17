"""`TimeFlux` (`TriggeredAbilityType.TimeFlux` = 1157) — passif de `thousTerminator` « Toth »
(HERO Thousand Sons, present dans `rl_duel.py build --list-pool` rank 17).

⚠ **DEUX VOLETS, DEUX CLASSES NATIVES DISTINCTES.** Ce module ne porte que le PREMIER.

## Volet REGEN (porte ici) — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxAbility`

i2 (autoritatif) : « At the beginning of his turn, Toth **regenerates 873 Health** plus an additional
amount equal to **the Damage of the last hit he received in the last enemy turn**. The total amount
restored **cannot exceed 4365 Health**. »

- `...TimeFluxAbility$$CreateTrigger` :

      <trigger de base factory@0xa0>  &  On(0x13 = 19 = TurnStart_Other, subject=1)

  `factory@0xa0` (cache de `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`) = **`OwnerIsActor`**
  — « le proprietaire est le joueur ENTRANT ». C'est le MEME cache que
  `IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateTrigger`, ou il est
  PROUVE live (`probe_203` : regen nulle au tour adverse). Noter l'ABSENCE de `IsDamaged(self)`
  (contraste LivingMetal) : sans effet observable, `HealUnitOperation` capant de toute facon a
  `hp_max` (heal = 0 a PV pleins).

- `...TimeFluxAbility$$CreateBehaviour` :

      Heal( source = self@0x148, targets = self@0x148,
            amount  = Min( Sum( Direct(GetVariableForLevel(cfg, 0x20 = hpToHeal,    abilityState)),
                                LastHitDamageTakenLastTurn(self@0x148) ),
                           Direct(GetVariableForLevel(cfg, 0x47 = maxHpToHeal, abilityState)) ),
            options = IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForRegenerate(
                          AbilityOrEffect(this.Id)) )

  `AbilityVariableType` : **0x20 = 32 = `hpToHeal`**, **0x47 = 71 = `maxHpToHeal`** — les deux dans
  `variablesAffectedByRarityBonus` -> rarity-scale. Le sélecteur de cible est `self@0x148` DIRECT
  (PAS un `HealableUnits(...)`) : aucun pre-filtre `HealableUnitsSelector` n'est donc porte ici,
  contrairement aux heals de `RevitalizingMalignancy`/`CombatRestoratives`.

- Substrat NEUF, entierement lu (cf. `runner/components.py`, champs `last_hit_damage_taken_*`) :
  `IdunBattle.Entities.Formulas.LastHitDamageTakenLastTurnFormula$$Calculate` rend
  `ActorStatisticsComponent + 0x70` ; `@+0x6c` est ecrit PAR COUP par
  `IdunBattle.Operations.ApplyDamageOperation$$Execute` (valeur = total du coup, PV + bouclier +
  armure-pool) et roule dans `@+0x70` par `IdunBattle.Operations.StartTurnOperation$$ResetUnit`.

## Volet GHOST-REVIVE (PORTE ailleurs — `loki/ghost_revive.py`, #213)

Classe native DISTINCTE : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxReviveAbility$$.ctor`
= `GhostReviveAbility` parametree par `EffectType.TimeFlux_Revive = 0x4a2 = 1186` (le ctor affiche
`EnvDefenderHealthBuffAbility..ctor` est un fold ICF — **ne pas se fier au nom**). Les DEUX
triggered-abilities sont derivees du MEME passiveAbility `TimeFlux`, d'ou les deux entrees de
`ABILITY_TRIGGERS["TimeFlux"]`. Arbres in extenso + les cinq retraits du ghost :
`loki/ghost_revive.py` ; RE de reference : `docs/rl/case-66-revive-in-place.md` §8.2.
La variable `TimeFlux.hp` (=2401 @L65) appartient a CE volet et n'est PAS lue ici : c'est le PV de
resurrection (`3290 = round(hp[L50] = 1828 x 180 %)`, live-valide).

DOCTRINE #149 : le `CreateTrigger` est COLLAPSE dans `matches()` ; le `CreateBehaviour` est un VRAI
ARBRE DSL (`Min`/`Sum`/`Const`/`LastHitDamageTakenLastTurn` + feuille `Heal`, qui appelle
l'Operation `HealUnitOperation`).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.formulas import LastHitDamageTakenLastTurn, Min, Sum
from .....entities.effects.magnitude import ability_var
from .....entities.selectors.tiles import Caster
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.stats import Heal
from ....components import OwnerComponent, StatsComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "TimeFlux"


def _passive_scaling(state: State, owner_id: int) -> tuple:
    """`(passive_ability_level, ability_variables_multiplier)` du porteur — `TimeFlux` est un PASSIF,
    donc le niveau des `GetVariableForLevel` est `passive_ability_level` (jamais l'actif)."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0, 100
    return (int(getattr(ctx, "passive_ability_level", 0) or 0),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def time_flux_hp_to_heal(state: State, owner_id: int) -> int:
    """`GetVariableForLevel(cfg, 0x20 = hpToHeal, abilityState)` (rarity-scale). 0 si absent."""
    lvl, mult = _passive_scaling(state, owner_id)
    return int(ability_var(ABILITY_ID, "hpToHeal", lvl, multiplier_pct=mult) or 0)


def time_flux_max_hp_to_heal(state: State, owner_id: int) -> int:
    """`GetVariableForLevel(cfg, 0x47 = maxHpToHeal, abilityState)` (rarity-scale). 0 si absent."""
    lvl, mult = _passive_scaling(state, owner_id)
    return int(ability_var(ABILITY_ID, "maxHpToHeal", lvl, multiplier_pct=mult) or 0)


def time_flux_regen_tree(hp_to_heal: int, max_hp_to_heal: int):
    """Arbre E de `...TimeFluxAbility$$CreateBehaviour` — MIRROR 1:1 :

        Heal( Self, Min( Sum( Direct(hpToHeal), LastHitDamageTakenLastTurn(Self) ),
                         Direct(maxHpToHeal) ) )

    Les deux `Direct(GetVariableForLevel(...))` sont FOLDES en `Const` (magnitude config resolue
    imperativement, meme regime qu'`ArcaneShield`/`DestroyerHive`) ; le noeud d'ETAT
    `LastHitDamageTakenLastTurn` reste un VRAI noeud, evalue a l'execution sur le dict d'unite live.

    La feuille `Heal` du port prend un `amount_fn` (callable ou scalaire) : on lui passe l'evaluation
    du noeud `Min`, ce qui preserve la structure de l'arbre. Pas de `guard` : le selecteur natif est
    `self@0x148` DIRECT, il n'y a AUCUN pre-filtre `HealableUnitsSelector` a mirrorer ici.

    ⚠ `options = HealBehaviourOptions$$ForRegenerate` = `(scope 1, removeEffects 0)` -- LU aux xrefs
    (`TimeFluxAbility$$CreateBehaviour` est l'un des SIX call-sites `ForRegenerate` du build). Le port
    tournait en `scope 0` jusqu'a #520, faute d'options sur la feuille : le cap de GROUPE
    `GetGroupUnitHealLimit` n'etait jamais consulte. Le porteur (`necroCryptek`) est mono-membre, donc
    l'ecart mesure est NUL sur lui -- ce qui est declare ici est la fabrique, pas un effet."""
    amount = Min(Sum(Const(int(hp_to_heal)), LastHitDamageTakenLastTurn(Caster())),
                 Const(int(max_hp_to_heal)))
    return Heal(Caster(), lambda entities, ectx: int(amount.evaluate(entities)),
                scope=1, remove_effects=False)


class TimeFluxRegenAbility(TriggeredAbility):
    """Volet REGEN — `OwnerIsActor & On(TurnStart_Other = 0x13 = 19)` -> `Heal(self, min(hpToHeal +
    lastHitDamageTakenLastTurn, maxHpToHeal))`. Cf. en-tete de module pour les arbres natifs."""
    event_id = int(EventTriggerType.TurnStart_Other)        # On(0x13 = 19)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `factory@0xa0` = OwnerIsActor : la regen ne fire qu'au debut du tour du PROPRIETAIRE.
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        oc = e.get_component(OwnerComponent)
        return oc is not None and ev.player_id is not None and oc.player == int(ev.player_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        hp_to_heal = time_flux_hp_to_heal(state, self.owner_id)
        max_hp = time_flux_max_hp_to_heal(state, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        time_flux_regen_tree(hp_to_heal, max_hp).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        heals = [p for n, p in ectx.emitted if n == "Heal"]
        if not heals:
            return None
        amount = int(heals[0].get("amount") or 0)
        healed = sum(int(h.get("healed") or 0) for h in (heals[0].get("heals") or []))
        if amount <= 0:
            return None                    # `Heal` no-ope a montant <= 0 (mirror du natif)
        return {"type": "time_flux_regen", "unit": int(self.owner_id),
                "hp_to_heal": hp_to_heal, "max_hp_to_heal": max_hp,
                "amount": amount, "healed": healed}
