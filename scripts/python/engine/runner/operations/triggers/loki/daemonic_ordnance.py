"""`DaemonicOrdnance_Crit` (triggered `0x4dc` = **1244**) -- le helper PASSIF de l'active
`0x47c` = 1148 `DaemonicOrdnance` (`blackForgefiend` -- Forgefiend, Black Legion, MACHINE OF WAR).
#521-r4 / #521-r10, case-521r1 Sec.5bis.

## Chemin de montage : `GetPassiveHelperAbility`, le SIXIEME chemin

`idun...StaticBattleRules.ActiveAbility$$GetPassiveHelperAbility` (dict `<statics>+0x78`, scalaire
`Nullable`) porte `1148 -> 1244`. Cote port : `PASSIVE_HELPER_ABILITY_TRIGGERS`, cle = le NOM
gameconfig de l'ACTIVE.

## UN id, DEUX classes natives -- et elles forment un CYCLE

Meme patron que `Lakrimae` / `DaemonfleshPlate` (une `TriggeredAbilityType` -> une LISTE
d'implementations), mais ici les deux classes vivent dans **`Active.Loki`**, pas `Triggered.Loki` --
c'est ce namespace qui avait fait conclure a une classe INTROUVABLE :

  * `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnance_AddCritChance` -- POSE le
    marqueur `1316` a l'init ;
  * `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnance_RemoveCritChance` -- le RETIRE
    quand le porteur a assez crite dans le tour.

⚠ **PIEGE D'ENUM, DANS LES DEUX SENS, ET IL MORD DANS CE MODULE MEME.** `0x524` est ici un
**`EffectType`** (`DaemonicOrdnance_ExtraCritChance`), alors que `TriggeredAbilityType(0x524)` =
`CalibaniteGreatsword_NormalAttackAdditionalDamage` -- **une autre entree du MEME dict** ; et
`0x4dc` est un `TriggeredAbilityType` (`DaemonicOrdnance_Crit`) alors qu'`EffectType(0x4dc)` =
`Contaminated`. Ecrire l'ordinal nu confondrait deux entrees voisines.

## `AddCritChance$$CreateTrigger` -- ABSENT DES DEUX TABLES, resolu par SLOT DE VTABLE

Le corps est fondu par l'ICF : ni `ghidra/functions.tsv` ni `frida/methods.tsv` ne portent
`DaemonicOrdnance_AddCritChance$$CreateTrigger` (mesure du build courant ; les DEUX
`$$CreateBehaviour` et le `RemoveCritChance$$CreateTrigger`, eux, y sont). Resolu par le slot
`0x2d8` (`probe_521r4_daemonic_ordnance_slots.py`, RPC `resolveVtableSlot`) : le proprietaire ghidra
du corps partage est
`IdunBattleLogic.Entities.Abilities.Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`
(nom ARBITRAIRE), dont le corps ENTIER est `return <DSLTriggers+0x30>`. Et
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` (RELU) construit ce champ :

    this+0x30 = On(0x21 = AbilityInit) & <this+0x70> & get_OwnerIsActor

`<DSLTriggers+0x70>` est le `YesTrigger` CONSTANT (element neutre de la conjonction, etabli par
#521-r4 -- cf. l'en-tete de `doctrina_imperatives.py`, qui porte le MEME trigger partage). Le
trigger effectif est donc `On(AbilityInit) & OwnerIsActor`.

## `AddCritChance$$CreateBehaviour` (MIRROR du decompile)

    AddStaticStatModifierEffectToOwner( Behaviors@dsl+0x78,
                                        effectType = 0x524 = 1316 DaemonicOrdnance_ExtraCritChance,
                                        statType   = 0x9   = CRIT_CHANCE,
                                        amount     = <DSLFormulas+0x18> = Direct(0),
                                        turns      = null,
                                        isHidden   = 0 )

**MAGNITUDE ZERO, et ce n'est pas une lecture de confort** : `<DSLFormulas+0x18>` est la constante
partagee `Direct(0)` qu'alloue `DSLFormulas$$.ctor` (`+0x18 = Direct(0)`, `+0x20 = Direct(1)`,
`+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)` -- cf.
`entities/triggers.py::is_mechanical`, qui lit `+0x20` par le meme canal). L'effet pose est donc un
**MARQUEUR** : il ne donne AUCUN crit-chance par lui-meme. Confirme live (`statModSources` sur
`blackForgefiend` au montage : `mods = {}`).

Ce que le marqueur COMMANDE, c'est l'etage [4] de l'active 1148, DEJA porte
(`runner/abilities/blacklegion.py::daemonic_ordnance_tree`) :

    [4] If( HasEffect(owner, 0x524),
            AddOrUpdateStaticStatModifierEffect(owner, 0x524, 9 = CRIT_CHANCE,
                Multiply(Sum(TotalActiveAbilityUsed(owner, 0x47c), Get(1)), Direct(extraCritChance))) )

-- d'ou l'oracle live de la magnitude : `critChance` **{} -> 20 -> 40** apres 0/1/2 casts
(`extraCritChance = 20`, et `TotalActiveAbilityUsed` est lu AVANT le compteur du cast courant).

## `RemoveCritChance$$CreateTrigger` / `$$CreateBehaviour` (MIRROR du decompile)

    CreateTrigger  = On(0xe = UnitPostAbility, ownerNeedsToBeAlive = 1) & get_OwnerIsCaster

    CreateBehaviour = If( AmountIsEqualOrGreater( CriticalHitsThisTurn(Owner@DSLSelectors+0x30),
                                                  Direct(GetHits2()) ),
                          RemoveEffect(Owner@+0x30, Nullable(0x524), 0),
                          null )

`GetHits2` = `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetHits2` = `AbilityConfiguration
$$GetNumberConstant(this.config@+0x20, 0x32 = nrOfHits_2)`.

## D'OU VIENT LA CONFIG -- meme mesure que pour `CalibaniteGreatsword`, refaite ici

`1244` n'a **AUCUNE configuration propre** : ni entree gameconfig (`GC.ability("DaemonicOrdnance_
Crit")` -> None), ni entree `BattleConfiguration.Abilities.{Active,Passive}Abilities` (mesure du
2026-08-15 sur `data/seed-bc.json` : `DaemonicOrdnance` est dans `ActiveAbilities`, aucun
`DaemonicOrdnance_Crit` nulle part). La seule configuration atteignable est celle de l'ACTIVE 1148,
et le gameconfig la corrobore : `DaemonicOrdnance.constants` porte `nrOfHits_2 = "3"` -- une
constante que l'active elle-meme ne lit PAS dans son `ExecuteBehaviour` (elle y lit `nrOfHits`), ce
qui est precisement la signature d'une constante posee POUR le helper. Meme situation, meme lecture
et meme conclusion que pour les trois autres helpers de ce dict (cf.
`calibanite_greatsword.py`).

## OBSERVABLE, et la LIMITE de chaque volet -- dite, pas masquee

  * **`RemoveCritChance` MORD sur le regime courant.** Son vecteur `On(0xe = UnitPostAbility)` est
    emis par les DEUX voies du port (#120), et l'effet `1316` qu'il retire est present sur
    `blackForgefiend` des le chargement : les unites du ROSTER arrivent par `load_state` depuis une
    capture live ou le natif a DEJA joue son `AbilityInit`. C'est ce volet qui ferme la boucle --
    sans lui, l'etage [4] de 1148 ferait croitre `critChance` de `extraCritChance` par cast
    INDEFINIMENT, le retrait natif ne se produisant jamais cote port.
  * **`AddCritChance` est INERTE sur le regime courant, exactement comme
    `DoctrinaImperatives_SetStart`** : le vecteur `On(AbilityInit)` n'est emis cote port qu'au SPAWN
    (`abilities/behaviours/summon.py`), et aucune unite portant l'active 1148 n'est spawnee. Il est
    inscrit parce que le registre natif l'inscrit et parce qu'il mordrait sur un spawn -- pas parce
    qu'il apporte un gain de comportement aujourd'hui. Le porter SEUL aurait ete le piege inverse
    (poser le marqueur sans jamais le retirer) : les deux volets partent ENSEMBLE ou pas du tout.

## FORME DU PORT (doctrine #149)

`CreateTrigger` COLLAPSE dans `matches` ; les deux `CreateBehaviour` sont des arbres DSL qui
APPELLENT les Operations deja portees (`AddEffectOperation` + `apply_change_stat` sous
`AddStaticStatModifierEffect` ; `RemoveEffectOperation` sous `RemoveEffect`).

1244 est une `TriggeredAbilityType` : elle n'entre NI dans `ABILITY_CLASSES`, NI dans
`TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE`.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddStaticStatModifierEffect, RemoveEffect
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.behaviours import If
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import CriticalHitsThisTurn
from .....entities.selectors.accessors import Owner
from .....entities.stats import StatType
from .....entities.triggers import AmountIsEqualOrGreater
from .....entities.triggered_ability_type import TriggeredAbilityType
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `PASSIVE_HELPER_ABILITY_TRIGGERS` = le NOM gameconfig de l'ACTIVE 0x47c = 1148.
DAEMONIC_ORDNANCE_ACTIVE = ActiveAbilityType.DaemonicOrdnance.name
#: `0x524` -- ⚠ un **`EffectType`** ici (cf. le piege d'enum de l'en-tete).
DO_EXTRA_CRIT_CHANCE = int(EffectType.DaemonicOrdnance_ExtraCritChance)          # 0x524 = 1316
#: `GetHits2()` = `GetNumberConstant(config, 0x32)`. La config atteignable est celle de l'ACTIVE.
DO_HITS2_KEY = "nrOfHits_2"


def daemonic_ordnance_hits2() -> int:
    """`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetHits2(this)` =
    `AbilityConfiguration$$GetNumberConstant(this.config@+0x20, 0x32 = nrOfHits_2)`.

    La config lue est celle de l'ACTIVE 1148 -- 1244 n'en a AUCUNE (cf. l'en-tete). Constante, donc
    ni niveau ni multiplicateur de rarete (`is_constant=True`). Config illisible -> `0`, ce qui rend
    le gate `crits >= 0` TOUJOURS vrai : c'est la degradation la plus proche du natif, qui LEVE sur
    une config nulle -- et sur ce chemin la constante existe (mesuree `3`)."""
    return int(ability_var(DAEMONIC_ORDNANCE_ACTIVE, DO_HITS2_KEY, is_constant=True) or 0)


def daemonic_ordnance_add_crit_chance_tree() -> AddStaticStatModifierEffect:
    """`DaemonicOrdnance_AddCritChance$$CreateBehaviour` -- MIRROR 1:1, un SEUL noeud :
    `AddStaticStatModifierEffectToOwner(1316, 9 = CRIT_CHANCE, <DSLFormulas+0x18> = Direct(0),
    turns = null, isHidden = 0)`.

    * `amount = Const(0)` = le `Direct(0)` PARTAGE du natif -- un MARQUEUR, pas un bonus. Ne PAS
      substituer `extraCritChance` ici : la magnitude vit dans l'etage [4] de l'active 1148, qui
      fait un `AddOrUpdate` par-dessus (cf. l'en-tete) ;
    * la factory `...ToOwner` fixe `source = targets = Owner@DSLSelectors+0x30` ; cote port, la voie
      STATIQUE prend de toute facon LA CIBLE pour source (son selecteur `+0x58` est un litteral nul,
      cf. `AddStaticStatModifierEffect`) -- meme entite, meme resultat ;
    * `turns = null` -> `duration_rounds`/`duration_turns` a `None` = duree par DEFAUT de l'effet."""
    return AddStaticStatModifierEffect(Owner(), DO_EXTRA_CRIT_CHANCE, int(StatType.CRIT_CHANCE),
                                       Const(0),
                                       name=EffectType.DaemonicOrdnance_ExtraCritChance.name)


def daemonic_ordnance_remove_crit_chance_tree() -> If:
    """`DaemonicOrdnance_RemoveCritChance$$CreateBehaviour` -- MIRROR 1:1 :

        If( AmountIsEqualOrGreater( CriticalHitsThisTurn(Owner@+0x30), Direct(GetHits2()) ),
            RemoveEffect(Owner@+0x30, Nullable(0x524), 0),
            null )

    La branche `else` est le **4e argument natif**, et il est NUL au call-site -> `otherwise=None`.
    `Direct(GetHits2())` est evalue A LA CONSTRUCTION cote port (constante de config, invariante
    pendant la bataille) la ou le natif alloue un noeud `Direct` : meme valeur, aucun etat lu."""
    return If(AmountIsEqualOrGreater(CriticalHitsThisTurn(Owner()),
                                     Const(daemonic_ordnance_hits2())),
              RemoveEffect(DO_EXTRA_CRIT_CHANCE, Owner()))


class DaemonicOrdnanceAddCritChanceAbility(TriggeredAbility):
    """`DaemonicOrdnance_AddCritChance` (une des deux classes natives du triggered 1244).

    OBSERVABLE : a l'init des abilities du porteur, pose le MARQUEUR 1316 (crit-chance +0) qui
    ARME l'etage [4] de l'active 1148. INERTE sur le regime courant -- cf. l'en-tete."""
    event_id = int(EventTriggerType.AbilityInit)            # `On(0x21)` (trigger partage +0x30)
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.DaemonicOrdnance_Crit)      # 0x4dc = 1244

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` -- sur ce vecteur le port pose `actor == target == l'unite qui
        # s'initialise` (cf. `dispatch/ability.py::ability_init_triggers`). Le 2e conjoint
        # `<DSLTriggers+0x70>` est le `YesTrigger` constant : element neutre, rien a porter.
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        daemonic_ordnance_add_crit_chance_tree().execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        placed = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        if not placed:
            return None
        return {"ability": "DaemonicOrdnance_AddCritChance", "owner": int(self.owner_id),
                "effect": DO_EXTRA_CRIT_CHANCE, "stat": int(StatType.CRIT_CHANCE)}


class DaemonicOrdnanceRemoveCritChanceAbility(TriggeredAbility):
    """`DaemonicOrdnance_RemoveCritChance` (la seconde classe native du triggered 1244).

    OBSERVABLE : a la CLOTURE de chaque ability du porteur, si le Forgefiend a porte au moins
    `nrOfHits_2` (= 3) coups CRITIQUES depuis le debut de son tour, le marqueur 1316 est retire --
    donc l'etage [4] de 1148 cesse de rafraichir le crit-chance, et la contribution deja posee est
    annulee par le revert per-source de `RemoveEffect`."""
    event_id = int(EventTriggerType.UnitPostAbility)   # `On(0xe, ownerNeedsToBeAlive = 1)`
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.DaemonicOrdnance_Crit)      # 0x4dc = 1244

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` -- l'ability qui se clot doit etre CELLE du porteur. Sur ce vecteur le
        # port pose `caster_id` en `actor_id` (cf. `dispatch/ability.py::unit_post_ability_triggers`).
        # `ownerNeedsToBeAlive = 1` est le gate de vivacite d'`EvaluateTriggerOperation$$
        # CanGetAbilityTrigger` : `fire_on_death` reste a FAUX (defaut), meme resultat, un seul cran.
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        daemonic_ordnance_remove_crit_chance_tree().execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = [p for n, p in ectx.emitted if n == "RemoveEffect" and p.get("removed")]
        if not removed:
            return None
        return {"ability": "DaemonicOrdnance_RemoveCritChance", "owner": int(self.owner_id),
                "effect": DO_EXTRA_CRIT_CHANCE,
                "removed": sum(int(p.get("removed") or 0) for p in removed)}
