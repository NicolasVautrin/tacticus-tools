"""`MedicusMinistorum` (`TriggeredAbilityType.MedicusMinistorum` = 1069 = 0x42d) -- passif de kit
d'`adeptHospitaller` << Isabella >> (HERO Sisterhood, Rare). RE : decompile ghidra, build
`rnca9r7q6c`.

## RECENSEMENT -- ce que le build possede REELLEMENT sous ce nom

Etabli par la COLONNE << classe declarante >> de `data/symbols/<build>/frida/methods.tsv` (le bloc
`methodPointers`), pas par grep de nom. DEUX classes, et ZERO homonyme egare (`methods.tsv` ne
porte aucune methode dont le NOM cite `MedicusMinistorum` mais dont la classe est autre) :

| classe                                                             | base (`classes.tsv`)                          | corps propres |
|--------------------------------------------------------------------|-----------------------------------------------|---------------|
| `IdunBattleLogic.Entities.Abilities.Active.Loki.MedicusMinistorumAbility` | `IdunBattle.Entities.Abilities.BaseTriggeredAbility` | 2             |
| `IdunBattle.AI.Playbook.Loki.MedicusMinistorumPlaybook`             | `AdjacentUnitPreferenceTriggeredAbilityPlaybook<...>` | 2             |

⚠ Le namespace dit `...Abilities.**Active**.Loki`, la BASE dit `BaseTriggeredAbility` : c'est un
PASSIF. La base se lit dans `classes.tsv`, jamais dans le namespace ni dans le nom du `.ctor`.
`BaseTriggeredAbility` expose 23 corps ; la classe n'en surcharge que **2** (`CreateTrigger`,
`CreateBehaviour`) -- aucun `GetEventTriggers`/`ShouldTrigger` propre.

## Les DEUX arbres natifs, lus verbatim

`IdunBattleLogic.Entities.Abilities.Active.Loki.MedicusMinistorumAbility$$CreateTrigger` :

    On(0x9 = Attack, ownerNeedsToBeAlive = 1)
      op_BitwiseAnd  AmountIsGreaterThanZero( <DSLFormulas+0x50> )       # = CurrentDamage
      op_BitwiseAnd  AreFriends(Target@<DSLSelectors+0x60>, Owner@<+0x30>,
                                comparisonType = 0, anyEntity = false)
      op_BitwiseAnd  IsAdjacent(Target@<+0x60>, Owner@<+0x30>, selectionType = 3)
      op_BitwiseAnd  op_LogicalNot( get_OwnerOrOwnerTileIsTarget )

`IdunBattleLogic.Entities.Abilities.Active.Loki.MedicusMinistorumAbility$$CreateBehaviour` :

    hp      = AbilityConfiguration.GetVariableForLevel(cfg, 0x20 = hpToHeal, abilityState,
                                                       fallbackToDefault = false)
    options = IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForRegenerate(
                  AbilityOrEffect(this.Id))
    return DSLBehaviors.Heal(healer   = Owner@<DSLSelectors+0x30>,
                             selector = Target@<DSLSelectors+0x60>,
                             amount   = DSLFormulas.Get(hp),
                             options  = options)

i2 : « Any friendly adjacent non-mechanical unit that takes Damage regenerates {hpToHeal} Health
afterwards, unless it is defeated. »

## Les SLOTS de contexte, IDENTIFIES et non devines

Les cinq slots lus ci-dessus le sont par leur OFFSET sur `DSLSelectors`/`DSLFormulas`/`DSLTriggers`,
et chacun est ancre sur une fonction NOMMEE du meme build :

  * `<DSLSelectors+0x30>` = **Owner** et `<+0x48>` = **Caster** -- ancres par
    `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster` = `AreEqual(+0x30, +0x48)` ;
  * `<DSLSelectors+0x60>` = **Target** -- ancre par `...$$get_OwnerIsTarget` = `AreEqual(+0x30, +0x60)` ;
  * `<DSLFormulas+0x50>` = **CurrentDamage** -- `IdunBattleLogic.Entities.DSLFormulas$$CurrentDamage`
    alloue le MEME pointeur de classe (`DAT_18336d9e8`) que `DSLFormulas$$.ctor` ecrit dans `+0x50`,
    et ce slot n'a AUCUNE autre xref dans le binaire (meme voie d'identification que celle qui a
    nomme `<DSLTriggers+0x28>` = `IsTurnOf(Owner)`) ;
  * `<DSLTriggers+0x20>` = **OwnerIsAlive** -- deja nomme par `entities/triggers.py::OwnerIsAlive`.
    Le natif ne l'ecrit pas ici : `DSLTriggers$$On(triggerType, ownerNeedsToBeAlive)` le porte, et
    l'appel passe `1`.

## `CurrentDamage` lit `totalDamage`, PAS `healthDamage` -- et l'extrapolation le ratait

`IdunBattle.Entities.Formulas.CurrentDamageFormula$$Calculate` a pour corps ENTIER :

    return Nullable<int>.GetValueOrDefault(entities + 0xe8);

Le champ `+0xe8` a ete LU dans `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` (la surcharge
a 33 parametres, tous NOMMES dans `frida/methods.tsv`), qui ecrit :

    *(this + 0xd8) = initialDamage;
    *(this + 0xe0) = healthDamage;
    *(this + 0xe8) = totalDamage;          <-- le champ que lit CurrentDamage
    *(this + 0xf0) = individualHitDamage;

⚠ L'INTERPOLATION depuis les ancres voisines rendait **`initialDamage`** : `blockedHits@0xfc`,
`hitIndex@0x108` et `movementSteps@0x11c` sont espaces exactement comme des champs sequentiels, ce
qui faisait remonter `healthDamage@0xe0 / initialDamage@0xe8 / totalDamage@0xf0`. Le ctor montre que
l'ordre MEMOIRE n'est PAS l'ordre de DECLARATION (`initialDamage` est AVANT `healthDamage`, et les
trois bools sont regroupes `wasCrit@0xf8 / hasUsedAttackDamage@0xf9 / wasBlock@0xfa`). Seule la
lecture tranche.

⚠ **ECART DE CANAL, ASSUME ET CHIFFRE** : le port ne thread PAS `totalDamage` sur son
`TriggerEvent` -- il porte `health_damage`, documente au site d'emission
(`dispatch/attack.py`) comme « part SANTE, bouclier deja defalque ». Le gate ci-dessous lit donc
`health_damage`. Consequence : une attaque qui ne consomme QUE du bouclier (`total > 0`,
`health == 0`) declenche le soin cote natif et PAS cote port -- divergence RESTRICTIVE, bornee aux
cibles porteuses d'un bouclier. Residu `#958-r1` (cf. `docs/rl/backlog.md`). Sur tout autre regime les
deux canaux sont non-nuls ensemble.

## Ce qui N'EST PAS dans l'arbre, et vit sous la feuille

Le tooltip promet « non-mechanical » et « unless it is defeated ». **Ni l'un ni l'autre n'est un
noeud de cet arbre** : le selecteur de cible est `Target@<+0x60>` NU (contraste avec son voisin de
forme `SanguinaryPriestAbility$$GetTargets`, qui soustrait explicitement `MechanicalUnits`). Les
deux gates vivent sous la feuille, dans `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed`
que `HealUnitOperation$$Execute` appelle -- deja porte
(`runner/abilities/attack_query.py::entity_can_be_healed`) :

    if (EntityExtensions.IsMachine(target)) return false;
    if (!( IsDamagedUnit(target) || ... )) return false;      # <- « unless it is defeated » / plein
    ...
    return UnitExtensions.IsAffectedByHealType(target, 0 = NonMechanical);   # <- « non-mechanical »

Recopier le filtre du voisin dans l'arbre l'aurait donc COMPTE DEUX FOIS, et surtout aurait rendu
STRICTE une regle que le natif applique sur un autre etage (`IsAffectedByHealType` laisse passer une
unite mecanique qui porte `AffectedByHealAndRepair`, la soustraction `MechanicalUnits` non).

## Doctrine #149

`CreateTrigger` = gates d'EVENEMENT -> COLLAPSE imperatif dans `matches()` (meme traitement que
`SanguinaryPriestAbility` et `HatefulAssaultAbility`). `CreateBehaviour` = VRAI ARBRE DSL : feuille
`Heal` portee, sur les accesseurs `Owner()` / `Target()` portes.

## Face DECISION

`IdunBattle.AI.Playbook.Loki.MedicusMinistorumPlaybook` -- porte dans
`engine/playbook/adjacent_unit_preference.py` (meme commit).

ASCII only (console cp1252).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effects.magnitude import ability_var
from .....entities.selectors.accessors import Owner, Target
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AreFriends, IsAdjacent
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.stats import Heal
from ....components import PositionComponent, StatsComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "MedicusMinistorum"
HP_TO_HEAL_KEY = "hpToHeal"                    # `AbilityVariableType.hpToHeal` = 0x20 = 32

#: 3e argument LITTERAL de `DSLTriggers$$IsAdjacent(Target, Owner, selectionType)`.
SELECTION_TYPE = int(UnitSelectionType.OnlyAliveAndTargetable)          # 3

#: `HealBehaviourOptions$$ForRegenerate` = `(scope 1, removeEffects 0)` -- LU sur `rnca9r7q6c`
#: (`+0x2c = 1`, `+0x30 = 0`), la MEME paire que son jumeau `RepairBehaviourOptions`.
HEAL_SCOPE = 1
HEAL_REMOVE_EFFECTS = False

_ON_ATTACK = int(EventTriggerType.Attack)                              # 0x9 = 9


def _passive_scaling(state: State, owner_id: int) -> tuple:
    """`(passive_ability_level, ability_variables_multiplier)` du porteur. `MedicusMinistorum` est un
    PASSIF -> le niveau des `GetVariableForLevel` est `passive_ability_level`, JAMAIS l'actif."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0, 100
    return (int(getattr(ctx, "passive_ability_level", 0) or 0),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def medicus_ministorum_hp_to_heal(state: State, owner_id: int) -> int:
    """`AbilityConfiguration$$GetVariableForLevel(cfg, 0x20 = hpToHeal, abilityState,
    fallbackToDefault = false)` -- le montant PLAT du soin (aucun `RandomAmount` ici, contrairement
    a `SanguinaryPriest` : le natif enveloppe la valeur dans `DSLFormulas$$Get(amount: Int32)`, la
    surcharge SCALAIRE, dont la signature est lue par `probe_951_call_targets.py`)."""
    lvl, mult = _passive_scaling(state, owner_id)
    return int(ability_var(ABILITY_ID, HP_TO_HEAL_KEY, lvl, multiplier_pct=mult) or 0)


def medicus_ministorum_behaviour_tree(hp: int):
    """`...MedicusMinistorumAbility$$CreateBehaviour` -- MIRROR 1:1 :

        Heal( healer   = Owner@<DSLSelectors+0x30>,
              selector = Target@<DSLSelectors+0x60>,
              amount   = Get(GetVariableForLevel(0x20 = hpToHeal)),
              options  = HealBehaviourOptions.ForRegenerate(AbilityOrEffect(this.Id)) )

    Le `healer` natif n'est PAS un parametre de la feuille portee : elle lit `entities.caster`, et
    pour un triggered `Owner == Caster` (`BaseTriggeredAbility$$Execute` execute le behaviour sur son
    propre porteur) -- c'est `entities_from_state(state, owner_id, ...)` qui le pose.

    AUCUNE `guard` : le natif ne met aucun filtre SUR LE SELECTEUR (cf. l'en-tete du module). Le
    volet non-mecanique/blesse est le gate `EntityCanBeHealed` de l'Operation, sous la feuille."""
    # `amount_fn` SCALAIRE : la feuille accepte « un scalaire deja resolu (fold d'un
    # `Direct(GetVariableForLevel(...))`) », ce qui est exactement la forme native ici
    # (`DSLFormulas$$Get(amount: Int32)`, surcharge scalaire).
    return Heal(Target(), int(hp), scope=HEAL_SCOPE, remove_effects=HEAL_REMOVE_EFFECTS)


class MedicusMinistorumAbility(TriggeredAbility):
    """`MedicusMinistorumAbility` (`TriggeredAbilityType` 0x42d = 1069, passif d'`adeptHospitaller`).

    `On(9 = Attack, ownerNeedsToBeAlive = 1) & AmountIsGreaterThanZero(CurrentDamage)
     & AreFriends(Target, Owner) & IsAdjacent(Target, Owner, 3) & !OwnerOrOwnerTileIsTarget`
    -> `Heal(Owner, Target, Get(hpToHeal), ForRegenerate)`.

    Cf. l'en-tete du module pour les deux arbres natifs, l'ancrage des slots et l'ecart de canal
    `totalDamage` / `health_damage`."""
    event_id = _ON_ATTACK
    # `BaseTriggeredAbility$$Execute` ecrit `AbilityOrEffect(this.Id)` avant le behaviour -> c'est ce
    # que lit `TriggeringAbilityIs`.
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.MedicusMinistorum)   # 0x42d = 1069

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """COLLAPSE du `CreateTrigger`. L'ordre suit celui du decompile ; chaque terme cite son noeud.

        Le sujet du soin est la CIBLE de l'attaque (`Target@<DSLSelectors+0x60>`), pas l'attaquant :
        le passif recompense l'allie QUI ENCAISSE."""
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        # `On(0x9, ownerNeedsToBeAlive = 1)` -- volet << owner vivant >> (`<DSLTriggers+0x20>`).
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:
            return False
        tid = ev.target_id
        if tid is None:
            return False
        tgt = state.get_entity(int(tid))
        if tgt is None:
            return False
        # `AmountIsGreaterThanZero(CurrentDamage)` -- `CurrentDamageFormula$$Calculate` =
        # `Nullable<int>.GetValueOrDefault(entities + 0xe8 = totalDamage)`. TRI-ETAT : le canal du
        # port est `health_damage` (part SANTE ; ecart documente en tete de module) ; `None` = non
        # threade sur cet event -> le natif lirait `GetValueOrDefault()` = 0, donc le gate FERME.
        # C'est FIDELE et non une degradation : un `Nullable` vide vaut 0, et `0 > 0` est faux.
        if int(ev.health_damage or 0) <= 0:
            return False
        # `!get_OwnerOrOwnerTileIsTarget` = `!( OwnerIsTarget | AreEqual(MainTileOfUnits(Owner),
        # Target) )` -- Isabella ne se soigne jamais elle-meme, ni quand la cible est SA tuile.
        if int(tid) == int(self.owner_id):
            return False
        opc = owner.get_component(PositionComponent)
        tpc = tgt.get_component(PositionComponent)
        if opc is not None and tpc is not None and (opc.col, opc.row) == (tpc.col, tpc.row):
            return False
        # Les DEUX derniers termes ne sont PAS recables a la main : ce sont des noeuds DSL deja
        # portes 1:1, et les evaluer preserve leur semantique exacte -- `AreFriends` compare les
        # equipes RESOLUES, `IsAdjacent` porte le quantificateur UNIVERSEL, les EMPREINTES completes,
        # la porte d'elevation et le filtre `selectionType` sur LES DEUX selecteurs (#433-r3). Un
        # `oc.team == oc2.team` + `neighbours()` ecrit ici serait un 5e mirror d'adjacence, ce que la
        # doctrine #149 interdit precisement.
        entities = entities_from_state(state, self.owner_id, int(tid), actor_id=ev.actor_id)
        # `AreFriends(Target@<+0x60>, Owner@<+0x30>, comparisonType = 0, anyEntity = false)`
        if not AreFriends(Target(), Owner()).should_trigger(entities):
            return False
        # `IsAdjacent(Target@<+0x60>, Owner@<+0x30>, selectionType = 3 = OnlyAliveAndTargetable)`.
        # Le `selectionType` filtre les DEUX selecteurs : le volet VIVANT de la cible est ICI -- une
        # unite tuee par le coup ne passe plus le selecteur, ce qui EST le « unless it is defeated »
        # du tooltip cote TRIGGER (le gate `IsDamagedUnit` de l'Operation en est le second cran).
        return bool(IsAdjacent(Target(), Owner(), SELECTION_TYPE).should_trigger(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        hp = medicus_ministorum_hp_to_heal(state, self.owner_id)
        if hp <= 0:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `AbilityEntities` du behaviour : caster == Owner@<+0x30> (Isabella, le SOIGNEUR que la
        # feuille relit comme `entities.caster`), target == Target@<+0x60> (l'allie qui a encaisse).
        entities = entities_from_state(state, self.owner_id, int(ev.target_id),
                                       actor_id=ev.actor_id)
        medicus_ministorum_behaviour_tree(hp).execute(entities, ectx)
        heals = next((p for n, p in ectx.emitted if n == "Heal"), None) or {}
        per_target = [{"target": h.get("target"), "healed": int(h.get("healed") or 0),
                       "amount": int(h.get("amount") or 0)}
                      for h in (heals.get("heals") or [])]
        if not per_target:
            return None
        return {"type": "medicus_ministorum_regen", "unit": int(self.owner_id),
                "hp_to_heal": hp, "heals": per_target,
                "healed": sum(h["healed"] for h in per_target)}
