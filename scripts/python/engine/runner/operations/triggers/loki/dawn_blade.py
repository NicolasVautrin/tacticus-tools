"""`DawnBlade` (relique `R_Crit_DawnBlade` de `tauFarsight`, `TriggeredAbilityType` 1501) -- volet
REPARATION (#317, 1re tranche de l'inventaire des 13 appelants de `DSLBehaviors$$Repair`).

================================================================================================
LE PIEGE, ET C'EST TOUT L'OBJET DE LA TRANCHE : LE NOM MENT, DEUX FOIS
================================================================================================
La classe native s'appelle `DawnBlade_HealAbility` et la variable qu'elle lit s'appelle `hpToHeal`.
Les DEUX sont trompeurs : l'artefact construit est un `IdunBattleLogic.Entities.DSLBehaviors$$Repair`,
donc la voie d'execution est `IdunBattle.Operations.RepairUnitOperation$$Execute`, PAS
`HealUnitOperation`. Classer par le NOM est exactement ce qui avait fait survivre le bug #310
(`LivingMetal` cable sur le soin) ; ici on classe par l'ARTEFACT.

Les deux Operations natives finissent sur le MEME `FillUpStatComponent$$FillUp`, donc la confusion
serait INVISIBLE en regime nominal. Elle se voit aux etages que la reparation a en plus (gate
`IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired`, `RepairModifier` de
`IdunBattle.Core.Services.DamagePrediction$$PredictRepair`, caps de `PredictRepair`) -- et au gate
`EffectType.Cursed` (79) que le SOIN a en plus, et qui joue A L'ENVERS (cf. `operations/repair.py`).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- les DEUX faces
================================================================================================
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DawnBlade_HealAbility$$CreateBehaviour` :

    v      = IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(cfg, 0x20, abilityState, 0)
             #   `AbilityVariableType` 0x20 = 32 = `hpToHeal`  (les autres appelants de `$$Repair`
             #   lisent 0x24 = 36 = `hpToRepair` -- ici c'est bien la variable « heal », sur un Repair)
    amount = IdunBattleLogic.Entities.DSLFormulas$$Get(v)                     # constante de l'arbre
    self   = <DSLSelectors+0x30>                                              # Owner
    opts   = IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRepair()   # (+0x10 = 0 scope,
                                                                                  #  +0x14 = 1 removeEffects)
    return   IdunBattleLogic.Entities.DSLBehaviors$$Repair(self, self, amount,
                                                           AbilityOrEffect(DawnBlade 1501), opts)

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DawnBlade_HealAbility$$CreateTrigger` :

      IdunBattleLogic.Entities.DSLTriggers$$On(0 = UnitDeath, ownerNeedsToBeAlive = true)
    & IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsActor
    & IdunBattleLogic.Entities.DSLTriggers$$IsDefeatedByMeleeAttack(<DSLSelectors+0x60>,
                                                                    countRevived      = false,
                                                                    countResurrected  = true)

ou `$$IsDefeatedByMeleeAttack` = `AmountIsGreaterThanZero(
`IdunBattleLogic.Entities.DSLSelectors$$UnitsDefeatedByMeleeAttack(sel, countRevived,
countResurrected))`, et `IdunBattle.Entities.Selectors.UnitsDefeatedByMeleeAttackSelector$$IsValidUnit`
retient une unite du selecteur ssi son marqueur natif « defaite par une attaque de MELEE » est pose
ET qu'elle est dans un etat de defaite (`UnitExtensions$$HasFlag(unit, 9)`, ou
`HealthComponent$$IsDead`, ou -- selon les deux drapeaux -- `HasFlag(unit, 0x14)` revivee /
`HasFlag(unit, 0xe)` ressuscitee).

================================================================================================
FORME DU PORT (doctrine #149)
================================================================================================
* `CreateTrigger` COLLAPSE imperativement dans `matches` (meme patron que BarbedOvipositor, l'autre
  consommateur porte d'`On(UnitDeath = 0)`) ;
* `CreateBehaviour` = un ARBRE DSL dont la FEUILLE `Repair` APPELLE `RepairUnitOperation` -- elle
  n'en re-ecrit aucun etage. La frontiere est le `.Execute` de la feuille.

LE GATE MORD-IL VRAIMENT ? (question qu'il faut se poser -- sur `LivingMetal` il etait TAUTOLOGIQUE)
Oui, et par DEUX chemins distincts :
  * `EntityCanBeRepaired` : la cible est le porteur (`Repair(self, self, ...)`), donc
    `UnitExtensions$$IsAffectedByHealType(unit, 1)` passe par `IsMechanical` (`tauFarsight` a le
    trait `Mechanical`) -- ce disjunct-la ne mord pas. MAIS, contrairement a `LivingMetal`, ce
    `CreateTrigger` **ne porte AUCUN `IsDamaged(self)`** : un porteur a PV PLEINS qui tue en melee
    passe le trigger et se fait REFUSER par le gate (`IsDamagedUnit` faux). C'est un refus REEL ;
  * `IsDefeatedByMeleeAttack` : un kill A DISTANCE ne declenche rien.

DEUX RESIDUS LEVES PAR #357 (le rail de la relique EQUIPEE)
  * **canal RELIQUE** -- le SEUL porteur non-npc, `tauFarsight`, obtient `DawnBlade` par l'item
    `R_Crit_DawnBlade` (`allowedUnits = ['tauFarsight']`), materialise cote natif dans
    `BattleConfiguration.Units[].TertiaryAbility`. Ce champ est desormais LU par le rail COMBAT :
    `snapshot._load_tertiary_abilities` (RPC `unitAbilityStates`, entrees de hierarchie **3**) seede
    `UnitContext.tertiary_ability`, que `collect_triggered_abilities` inscrit comme CINQUIEME chemin
    de registration -- mirror de la branche tertiaire d'`IdunBattle.Entities.Factories.UnitFactory$$
    AddConfiguredAbilities`. Le canal (`load_state(ability_states=...)`) est ON PAR DEFAUT depuis
    #363 des qu'un transport ambiant est lie (`snapshot.bind_live_rpc`, pose par le harnais de
    test) ; un `State` nu, ou une capture rejouee hors harnais live, ne voit que la voie
    `relicAbilities` du gameconfig (les 5 npc `tauBossFarsight*` / `tauNpcFarsight`, qui l'ont EN
    DUR) -- exactement comme avant #357.
  * **niveau de la variable** -- `hpToHeal` a 10 entrees (niveaux de RELIQUE 1..10), indexees
    nativement par `BC.Units[].TertiaryAbilityLevel`. Le port lisait `passive_ability_level` (50 sur
    tout runner normalise), qu'`ability_var` clampait au dernier palier : la relique rendait
    TOUJOURS `hpToHeal[10]`, quel que soit son niveau. `triggered_ability_state` (mirror des trois
    `AbilityState` d'`UnitFactory$$Build`) rend maintenant le couple TERTIAIRE exact
    (`TertiaryAbilityLevel`, `TertiaryAbilityVariablesMultiplierPercentage` +0x78) quand l'ability
    arrive par l'item equipe, et le couple PASSIF sinon. Mesure : `probe_357_relic_rail.py`.

RESIDUS NOMMES
  * **marqueur « defaite par attaque de MELEE »** -- le natif lit un CHAMP persistant pose sur la
    victime ; le port n'a aucun canal melee sur le vecteur `On(UnitDeath = 0)`
    (`unit_death_triggers` pose `ranged=False` en dur). Le port evalue donc la nature du coup
    POSITIONNELLEMENT via `_is_ranged_position` -- le meme mirror que celui de
    `IdunBattleLogic.Entities.DSLTriggers$$IsMeleeAttack` (position-based) deja utilise ailleurs
    dans le runner. APPROXIMATION ASSUMEE, et elle est du bon cote : omettre le gate rendrait le
    trigger PERMISSIF (il firerait sur un kill a distance), la degradation que la doctrine condamne.
  * `countRevived = false` / `countResurrected = true` -- les deux drapeaux d'
    `UnitsDefeatedByMeleeAttackSelector` (`HasFlag(unit, 0x14)` / `HasFlag(unit, 0xe)`) ne sont pas
    modelises : dans tout regime porte, une victime REVIVEE ne parvient pas jusqu'a `On(UnitDeath)`
    (la garde revive de `damage.py::_kill_unit_operation` court-circuite la sequence apres
    `On(PreUnitDeath)`), donc la seule branche atteignable est `HealthComponent.IsDead`.
  * `source = AbilityOrEffect(DawnBlade 1501)` (attribution) -- aucun observable d'etat porte, non
    modelise (meme choix que la feuille `Repair` de #299).
  * `DawnBlade_InitAbility` (2e classe native du MEME id 1501, `AddEffect(0x5dd)`) et l'effet
    `IdunBattle.Entities.Effects.Loki.DawnBladeEffect` (`EffectType` 1501 `DawnBlade_ExtraDmg`, +degat
    melee cumulatif, 2 triggers propres) sont HORS PERIMETRE de cette tranche (« appelants de
    `$$Repair` ») -- ils ne construisent aucun `Repair`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.selectors.accessors import Owner
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....components import StatsComponent, UnitComponent
from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.stats import Repair
from ..base import (TriggeredAbility, TriggerEvent, triggered_ability_state,
                    defeated_by_melee)
from .....entities.effects.magnitude import ability_var

ABILITY_ID = "DawnBlade"
HP_TO_HEAL_KEY = "hpToHeal"      # `AbilityVariableType` 0x20 = 32 -- le NOM dit heal, l'artefact repare
REPAIR_SCOPE = 0                 # `RepairBehaviourOptions$$ForRepair` : +0x10 = 0
REPAIR_REMOVE_EFFECTS = True     # ...                                   +0x14 = 1

_ON_UNIT_DEATH = int(EventTriggerType.UnitDeath)          # `On(0, ownerNeedsToBeAlive = true)`


def dawn_blade_behaviour_tree(amount: int) -> Repair:
    """`...DawnBlade_HealAbility$$CreateBehaviour` = `Repair(Owner@0x30, Owner@0x30, Get(v), ForRepair)`.

    `amount` est resolu par l'APPELANT parce que le natif le resout lui aussi AVANT de batir l'arbre
    (`GetVariableForLevel` puis `DSLFormulas$$Get`) : c'est une CONSTANTE de l'arbre, pas un noeud
    paresseux -- meme forme que `FabricatorClawArray`."""
    return Repair(Owner(), amount, scope=REPAIR_SCOPE, remove_effects=REPAIR_REMOVE_EFFECTS)


def hp_to_heal(state: State, owner_id: int) -> int:
    """`AbilityConfiguration$$GetVariableForLevel(cfg, 0x20 = hpToHeal, abilityState, 0)`.

    L'`abilityState` est celui sous lequel l'ability est MONTEE, et `triggered_ability_state` mirrore
    le choix qu'en fait `IdunBattle.Entities.Factories.UnitFactory$$Build` : etat TERTIAIRE
    (`TertiaryAbilityLevel` / `TertiaryAbilityVariablesMultiplierPercentage`) quand `DawnBlade`
    arrive par l'item relique EQUIPE, etat PASSIF quand elle est cablee en dur sur un npc
    (`gameconfig.relicAbilities`) -- ou quand le canal tertiaire n'a pas ete fourni au chargement.

    `hpToHeal` n'est PAS dans `variablesAffectedByRarityBonus` du gameconfig de `DawnBlade` -> le
    `multiplier_pct` ne s'applique pas (`ability_var` gate l'application sur cette liste) ; on le
    passe quand meme, parce que c'est le natif qui decide -- pas nous. 0 si l'unite / son contexte /
    la variable manquent -> la feuille `Repair` est alors un no-op (`amount > 0` est sa garde)."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or getattr(sc, "ctx", None) is None:
        return 0
    lvl, mult = triggered_ability_state(state, owner_id, ABILITY_ID)
    return int(ability_var(ABILITY_ID, HP_TO_HEAL_KEY, lvl, multiplier_pct=mult) or 0)


class DawnBladeHealAbility(TriggeredAbility):
    """`DawnBlade_HealAbility` -- quand le porteur DEFAIT une unite par une attaque de MELEE, il se
    REPARE `hpToHeal[niveau]` PV (`Repair`, pas `Heal` : cf. l'en-tete du module).

    Le montant passe par `RepairUnitOperation`, donc par le gate `EntityCanBeRepaired` et par le
    `RepairModifier` de `PredictRepair` -- un porteur a PV PLEINS ne recupere RIEN (`IsDamagedUnit`),
    contrairement a ce qu'un cablage sur `HealUnitOperation` aurait laisse passer."""
    event_id = _ON_UNIT_DEATH
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.DawnBlade)          # 0x5dd = 1501

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : le porteur est l'ACTEUR de l'evenement de mort = le TUEUR
        # (`unit_death_triggers` construit l'event avec `actor = killer`, `target = dying`).
        if ev.actor_id != self.owner_id:
            return False
        dying = ev.dying_id if ev.dying_id is not None else ev.target_id
        if dying is None or dying == self.owner_id:
            return False
        victim = state.get_entity(dying)
        owner = state.get_entity(self.owner_id)
        if victim is None or owner is None:
            return False
        # `UnitsDefeatedByMeleeAttackSelector$$IsValidUnit` -- branche `HealthComponent$$IsDead` (les
        # deux drapeaux revive/resurrect ne sont pas modelises, cf. residus de l'en-tete).
        vuc = victim.get_component(UnitComponent)
        if vuc is not None and vuc.alive:
            return False
        # ... et le marqueur « defaite par une attaque de MELEE ».
        # ⚠ **IL EST DESORMAIS LU (#462-...-r6-r2), l'approximation n'est plus qu'un REPLI** -- meme
        # rebranchement que `loki/possession.py`, qui l'annoncait explicitement comme << NON FAIT
        # ici (autre foyer) >>. Le natif lit le byte `UnitComponent+0x178`
        # (`DefeatedByMeleeAttack`), que `IdunBattle.Operations.KillUnitOperation$$Execute` ecrit
        # INCONDITIONNELLEMENT avec `rangeType.HasValue && rangeType == Melee(1)` ; le port le tient
        # sur les DEUX faces (`damage.py::_kill_unit_operation` en simulation,
        # `snapshot._load_death_sources` depuis `decisionView.units[].defeatedByMelee`).
        # CE QUE CA CHANGE, MESURE LIVE : sur un CRUSH le marqueur natif vaut **False** (la voie ne
        # transporte aucun `AttackRangeType`), alors que l'approximation positionnelle disait
        # << melee >> -- le mover est SUR la tuile du crushe, donc a distance 0. Le port faisait donc
        # fire une reparation que le natif ne fait pas.
        # TRI-ETAT conserve : `None` = etat charge sans le champ -> REPLI positionnel, nomme.
        # FOYER UNIQUE `triggers/base.py::defeated_by_melee` (2e site : `loki/possession.py`).
        return defeated_by_melee(state, int(self.owner_id), int(dying))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        amount = hp_to_heal(state, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `Repair(self, self, ...)` : `mechanic` (le REPARATEUR) et la cible sont le MEME
        # `Owner@0x30` au decompile -> `entities_from_state(state, owner)` pose `caster = owner`.
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        dawn_blade_behaviour_tree(amount).execute(entities, ectx)
        emitted = next((p for (n, p) in ectx.emitted if n == "Repair"), {})
        repairs = emitted.get("repairs") or []
        repaired = sum(int(r.get("repaired") or 0) for r in repairs)
        if repaired <= 0:
            return None                       # gate `EntityCanBeRepaired` / porteur a PV pleins
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "victim": None if ev.dying_id is None else int(ev.dying_id),
                "amount": int(amount), "repairs": repairs, "repaired": repaired}
