"""`Neuroparasite` -- la POSE du parasite et sa MONTEE EN NIVEAU (#462-r4b-r1-r1-r1).

Passif de `tyranNeurothrope` << Neurothrope >> (HERO Tyranids, AU POOL) et de 6 npc.
`TriggeredAbilityType.Neuroparasite = 0x49f = 1183` (l'ABILITY) pose
`EffectType.Neuroparasite = 0x4c2 = 1218` (l'EFFET, sur la victime) -- deux enums HOMONYMES, a ne
jamais confondre (le playbook, lui, lit l'EFFET : cf. `engine/playbook/neuroparasite.py`).

Ce module ferme le residu nomme au §8 de `docs/rl/case-462-r4b-r1-r1-rayon-de-souffle-additif-
defenseur.md` : la MAGNITUDE de l'additif defenseur etait juste (PR #553) mais la mesure n'avait ete
possible que parce que la POSE venait du NATIF et que l'etat etait seede. En self-play 100 % porte,
le parasite n'apparaissait JAMAIS, et tous les bras mesures etaient au NIVEAU 1.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- TROIS artefacts natifs, TROIS `Triggered()`
================================================================================================
Slots `DSLSelectors` (nommes de longue date par `IdunBattleLogic.Entities.DSLTriggers$$
get_OwnerIsActor` = `AreEqual(+0x30, +0x40)`, cf. `docs/rl/case-303-fabricator-claw-array.md`) :
`+0x30 Owner · +0x38 Effect · +0x40 Actor · +0x48 Caster · +0x60 Target`.
Slots `DSLFormulas` (lus dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`) :
`+0x18 Direct(0) · +0x20 Direct(1) · +0x28 Direct(2) · +0x30 Direct(100) · +0x38 Direct(-1)`.

## 1. LA POSE -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.NeuroparasiteAbility`

`$$CreateTrigger` :

    On(9 = Attack, 1)
      & get_OwnerIsCaster
      & NOT HasEffect(Target@0x60, 0x4c2, onlyActive: 0, 6)
      & IsUnit(Target@0x60)
      & CurrentAttackDamageProfilesContain(0xd = Psychic, 0)
      & NOT (get_OwnerIsActor & get_OwnerIsTarget)

`$$CreateBehaviour` :

    AddBondEffect( 0x4c2 = 1218,
                   abilityState = BaseTriggeredAbility$$get_AbilityStateReference(this),
                   source       = Owner@0x30,
                   targets      = Target@0x60,
                   bondedEntity = Owner@0x30,
                   options      = <struct 0x20 octets ZERO-initialisee> )

Les options sont un `Nullable` VIDE (les 32 octets du local sont mis a zero juste avant l'appel) ->
`IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect` en tire un `GetValueOrDefault` nul, donc
**AUCUNE duree** : la duree retombe sur `DefaultAmountOfRounds(0x4c2)`, absente -> effet PERMANENT
(`remaining = 0`), retire par TRIGGER seulement. C'est ce que le live #86 observait deja.

`On(9)` = `EventTriggerType.Attack`, l'event de CLOTURE de toute attaque
(`IdunBattle.Operations.FinishAttackOperation$$Execute`, emis PAR CIBLE) -- d'ou le fait, mesure par
la case-462-r4b-r1-r1 §6, que le parasite ne joue son additif qu'a la frappe SUIVANTE.

## 2. LA MONTEE EN NIVEAU -- `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect`

`$$CreateHandleTriggerAbilitiesInternal` ajoute DEUX `Triggered()` a l'`ArraySet` herite d'
`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal` :

    Triggered( BaseEffect$$On(9) & GetDamageTakenTrigger(),      GetIncreaseLevelBehaviour() )
    Triggered( BaseEffect$$On(0x3d) & GetPreEffectAddedTrigger(), GetIncreaseLevelBehaviour() )

avec (decompiles LUS, pas deduits) :

    $$GetDamageTakenTrigger    = get_OwnerIsTarget & CurrentAttackDamageProfilesContain(0xd)
    $$GetPreEffectAddedTrigger = get_OwnerIsTarget & TriggeringEffectIs(0x429 = 1065 Pinned)

`0x3d = 61 = EventTriggerType.PreEffectAdded`. Sur la POSE d'un effet, `IdunBattle.Operations.
AddEffectOperation$$Execute` ecrit le MEME `AbilityOrEffect(effectType)` dans `+0x60`
(`CurrentAbility`) ET `+0x98` (`TriggeringAbility`) -> `TriggeringEffectIs` est bien renseigne sur
ce vecteur (asymetrie #306 : au RETRAIT il ne le serait pas).

`$$GetIncreaseLevelBehaviour` :

    IncreaseEffectLevel( effect = Effect@0x38,
                         amount = Direct(1)@DSLFormulas+0x20,
                         max    = <l'expression de $$GetMaximumLevel> )

`$$GetMaximumLevel` (corps IDENTIQUE a la sous-expression `max` ci-dessus -- ghidra montre les deux
fonctions bit-pour-bit) :

    Sum( ConfigVar(0x4c, GetAbilityState(effect), <config@effet+0x60>),
         If( ActorHasTriggeredAbility(ABondEffect$$BondedEntitySelector, 0x5d7),
             ConfigConst(0x5d7, ABondEffect$$BondedEntitySelector, 0x73),
             Direct(0)@DSLFormulas+0x18 ) )

QUALIFICATION DES CLES (par EXCLUSION sur la config REELLEMENT SERVIE, pas sur le seul gameconfig) :

* `ConfigVar(0x4c, ...)` -- la surcharge visee est `ConfigVar(variableType, abilityState, config)`
  (4 arguments), donc `0x4c` indexe les VARIABLES de la config de l'EFFET = celle de
  `Neuroparasite`. `data/seed-bc.json` -> `Abilities.PassiveAbilities.Neuroparasite.Variables` =
  **exactement deux entrees**, `extraDmg` et `buffMaxLevel`. `extraDmg` est l'index `8`, atteste
  bit-exact live (#86 puis #462-r4b-r1-r1). Donc **`0x4c = buffMaxLevel`** -- et c'est la SEULE
  ability du BC qui porte `buffMaxLevel` en VARIABLE (les autres, dont `TerrifyingCrescendo`, la
  portent en CONSTANTE, lue par `GetNumberConstant(0x62)`). `buffMaxLevel[L50] = 15` = le
  « max 15 niveaux » que la docstring de `NeuroparasiteEffect` attestait deja.
* `ConfigConst(0x5d7, unit, 0x73)` -- surcharge `ConfigConst(abilityType, unit, variableType)`
  (4 arguments) : la config lue n'est PAS celle de l'effet mais celle de l'ability `0x5d7`.
  `0x5d7 = 1495` doit etre qualifie : `TriggeredAbilityType.NornCrown` (le noeud est
  `ActorHasTriggeredAbility`, donc un `TriggeredAbilityType`), surtout PAS
  `EffectType.HunterOfSouls_ExtraDamage` (1495 aussi). `gameconfig.NornCrown.constants` = **une
  seule entree**, `effectLevel = 1` -> **`0x73 = effectLevel`**.

=> `max = buffMaxLevel[niveau du passif du Neurothrope] + (1 si le Neurothrope porte NornCrown)`.
`NornCrown` est une RELIQUE (variables sur 10 paliers) : hors montage relique le terme vaut 0.

## 3. Ce qui reste NON PORTE, et pourquoi (residus NOMMES)

`ABondEffect$$CreateHandleTriggerAbilitiesInternal` construit jusqu'a TROIS triggers de RETRAIT,
chacun garde par un VIRTUEL de la classe d'effet (slots `+0x748`, `+0x728`, `+0x738` de la vtable) :

    (a) <0x748>()          -> Triggered( NOT AmountIsZero(BondedEntity) & (On(2) | On(0x25))
                                         & IsEntityWithIdTarget(BondedEntity), RemoveEffect(Effect) )
    (b) <0x728>() : Nullable<int> ; si HasValue ->
                              Triggered( NOT IsInRange(Owner@0x30, BondedEntity, Direct(value))
                                         & NOT AmountIsZero(BondedEntity) & On(0x1d),
                                         RemoveEffect(Effect) )
    (c) <0x738>()          -> Triggered( NOT IsAdjacent(Owner@0x30, BondedEntity, 3)
                                         & NOT AmountIsZero(BondedEntity) & On(0x1d),
                                         RemoveEffect(Effect) )

Aucun de ces trois virtuels n'apparait sous le nom `NeuroparasiteEffect$$*` dans les tables -- ce qui
ne prouve RIEN (corps triviaux DEDUPLIQUES par IL2CPP : un `xor eax,eax ; ret` pour un bool faux, un
`Nullable` vide).

RESOLU par #462-r4b-r1-r1-r1-r1, en enumerant `class_get_methods` NIVEAU PAR NIVEAU de la chaine de
parents (le patron << comparer le POINTEUR de slot >> ne s'applique PAS ici : la base `ABondEffect`
est abstraite, sa vtable n'est jamais materialisee). Les trois virtuels sont NOMMES -- `+0x728
get_Range`, `+0x738 get_Adjacent`, `+0x748 get_RemoveOnBondedEntityDeath` -- et pour
`NeuroparasiteEffect` ils valent respectivement `Nullable` VIDE, `false`, **`true`**.

Donc, sur CE porteur, SEUL le trigger (a) est construit, et il EST porte :
`engine/runner/operations/triggers/bond_removal.py` (`BondRemoveOnBondedEntityDeath`, inscrit dans
`EFFECT_TRIGGERS[1218]` par derivation de `BOND_REMOVAL_GATES`). Confronte live : la mort du
Neurothrope retire le parasite, celle d'une unite TIERCE ne le touche pas -- des deux cotes.
(b) et (c) restent NON CONFRONTES et non portes ; residus nommes dans
`docs/rl/case-462-r4b-r1-r1-r1-r1-retrait-bond.md` §6.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, UnitComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddBondEffect, IncreaseEffectLevel
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.damage_profile_type import DamageProfileType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....entities.triggered_ability_type import (TriggeredAbilityType,
                                                  entity_triggered_ability_ids)
from ..base import EffectTrigger, TriggerEvent, TriggeredAbility

NEUROPARASITE_ABILITY = "Neuroparasite"
NEUROPARASITE_EFFECT = int(EffectType.Neuroparasite)             # 0x4c2 = 1218 (l'EFFET)
_NEUROPARASITE_TRIGGERED = int(TriggeredAbilityType.Neuroparasite)   # 0x49f = 1183 (l'ABILITY)
_PSYCHIC = int(DamageProfileType.Psychic)                        # 0xd = 13
_PINNED = int(EffectType.Pinned)                                 # 0x429 = 1065
# `ActorHasTriggeredAbility(BondedEntity, 0x5d7)` -- QUALIFIE `TriggeredAbilityType`, pas
# `EffectType.HunterOfSouls_ExtraDamage` qui vaut 1495 lui aussi (le noeud lit le kit DECLENCHE).
_NORN_CROWN = int(TriggeredAbilityType.NornCrown)                # 0x5d7 = 1495
_NORN_CROWN_ABILITY = "NornCrown"
_NORN_CROWN_CONST = "effectLevel"                                # `ConfigConst(0x73)` (seule constante)
_MAX_LEVEL_VAR = "buffMaxLevel"                                  # `ConfigVar(0x4c)` (2e des 2 variables)
_LEVEL_INCREMENT = 1                                             # `Direct(1)@DSLFormulas+0x20`


def _profiles_contain(ev: TriggerEvent, profile_id: int) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$CurrentAttackDamageProfilesContain(0xd, 0)` -- le SET
    des profils de TOUTE l'attaque (arme + coups bonus), threade par `finish_attack_triggers` dans
    `ev.profiles`. Repli sur `ev.profile` seul quand le canal n'est pas renseigne (meme convention
    que les autres consommateurs, cf. le commentaire `profiles` de `TriggerEvent`)."""
    name = DamageProfileType(profile_id).name
    got = ev.profiles if ev.profiles is not None else ({ev.profile} - {None})
    return name in got


def _neuroparasite_instance(state: State, owner_id: int):
    """L'instance 1218 NON CONSOMMEE portee par `owner_id`, ou None.

    C'est le port du selecteur `Effect@DSLSelectors+0x38` = l'entite-effet COURANTE que le natif
    passe a `IncreaseEffectLevel` et a `GetAbilityState`. COLLAPSE ASSUME, identique a celui de
    `ChronometronExtraDamageRemove` : le gate << deja present >> d'`AddEffectOperation` garantit au
    plus UNE instance non consommee de 1218 par unite, donc « l'instance courante » et « l'instance
    du type sur ce porteur » coincident."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(owner_id), []):
        if not e.consumed and e.effect_type == NEUROPARASITE_EFFECT:
            return e
    return None


def neuroparasite_maximum_level(state: State, eff) -> Optional[int]:
    """`IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$GetMaximumLevel` :

        Sum( ConfigVar(0x4c = buffMaxLevel, GetAbilityState(effect), <config de l'effet>),
             If( ActorHasTriggeredAbility(BondedEntity, 0x5d7 = NornCrown),
                 ConfigConst(0x5d7, BondedEntity, 0x73 = effectLevel),
                 Direct(0) ) )

    `GetAbilityState(effect)` = l'`AbilityStateReference` BAKEE dans l'entite-effet a la pose (le
    3e argument d'`AddBondEffect`) -- donc le niveau du passif du NEUROTHROPE, pas celui de sa
    victime. Cote port c'est `eff.ability_level`, renseigne par `scale_from_source=True`.
    `buffMaxLevel` n'est PAS dans `variablesAffectedByRarityBonus` -> le multiplier est un no-op
    (`ability_var` ne l'applique qu'aux variables listees), on le passe quand meme pour rester le
    calque strict.

    Rend `None` si la variable est introuvable -> l'appelant passe alors `max_level=None`, ce que
    `IncreaseEffectLevelOperation` traite comme « pas de cap » (`!max.HasValue`). C'est FIDELE au
    natif dans le seul regime ou ca arrive (config absente = `TryGetVariableArrayForLevel` echoue),
    et ca ne peut qu'etre PERMISSIF, jamais bloquant."""
    lvl = getattr(eff, "ability_level", None)
    mult = int(getattr(eff, "ability_variables_multiplier", 100) or 100)
    base = ability_var(NEUROPARASITE_ABILITY, _MAX_LEVEL_VAR, lvl, multiplier_pct=mult)
    if base is None:
        return None
    # `If(ActorHasTriggeredAbility(BondedEntity, NornCrown), ConfigConst(effectLevel), Direct(0))`.
    # `BondedEntity` = `ABondEffect$$BondedEntityId` = le champ `+0x10` du composant de bond, que le
    # port porte sur l'instance (`BaseEffect.bonded`, ecrit par `AddEffectOperation`).
    bonded = getattr(eff, "bonded", None)
    if bonded is None:
        return int(base)
    be = state.get_entity(int(bonded))
    sc = be.get_component(StatsComponent) if be is not None else None
    if sc is None:
        return int(base)
    ids = entity_triggered_ability_ids(sc.ctx, getattr(sc.ctx, "visual_id", None))
    if _NORN_CROWN not in ids:
        return int(base)
    bonus = ability_var(_NORN_CROWN_ABILITY, _NORN_CROWN_CONST, None, is_constant=True)
    return int(base) + int(bonus or 0)


def neuroparasite_bond_tree() -> AddBondEffect:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.NeuroparasiteAbility$$
    CreateBehaviour` :

        AddBondEffect( 0x4c2 = 1218,
                       abilityState = get_AbilityStateReference(this),
                       source       = Owner@DSLSelectors+0x30,
                       targets      = Target@DSLSelectors+0x60,
                       bondedEntity = Owner@DSLSelectors+0x30,
                       options      = <vide> )

    `entities_from_state(state, owner, target)` pose `caster = owner` -> `Caster()` EST le selecteur
    `Owner@0x30` sur ce vecteur (une triggered a Owner == Caster).
    `duration_rounds=None` = les options natives VIDES -> `DefaultAmountOfRounds(0x4c2)`, absente ->
    PERMANENT. `scale_from_source=True` = le 3e argument natif `abilityState` : l'entite-effet BAKE
    l'etat d'ability du NEUROTHROPE, ce que relit `GetAbilityState(effect)` dans `GetMaximumLevel`.

    Rendu par une USINE (patron `barbed_ovipositor_spawn_tree`) et non construit inline : c'est ce
    qui rend l'arbre INSPECTABLE par un garde offline. Un garde qui lirait le TEXTE du `execute_*`
    ne pourrait pas rougir -- il matcherait ses propres commentaires."""
    return AddBondEffect(NEUROPARASITE_EFFECT, EffectType.Neuroparasite.name,
                         Caster(), Target(), duration_rounds=None, bonded_ref=Caster(),
                         scale_from_source=True)


def neuroparasite_increase_level_tree(max_level: Optional[int]) -> IncreaseEffectLevel:
    """Arbre de `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$GetIncreaseLevelBehaviour` :

        IncreaseEffectLevel( effect = Effect@DSLSelectors+0x38,
                             amount = Direct(1)@DSLFormulas+0x20,
                             max    = $$GetMaximumLevel() )

    Frontiere #149 : feuille DECLARATIVE ici, le mutateur
    `IdunBattle.Operations.IncreaseEffectLevelOperation` EN DESSOUS."""
    return IncreaseEffectLevel(NEUROPARASITE_EFFECT, Caster(), _LEVEL_INCREMENT, max_level)


def _increase_level(state: State, owner_id: int) -> Optional[dict]:
    eff = _neuroparasite_instance(state, owner_id)
    if eff is None:
        return None                              # plus d'instance -> le behaviour natif est un no-op
    ectx = ExecutionContext(state=state, rng=state.rng)
    neuroparasite_increase_level_tree(neuroparasite_maximum_level(state, eff)).execute(
        entities_from_state(state, owner_id, owner_id), ectx)
    lvls = [p for n, p in ectx.emitted if n == "IncreaseEffectLevel"]
    if not lvls:
        return None
    return {"effect": NEUROPARASITE_ABILITY, "owner": int(owner_id),
            "level": lvls[-1].get("level"), "max_level": lvls[-1].get("max_level")}


class NeuroparasiteAddBondEffectAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.NeuroparasiteAbility` -- la POSE.

    `CreateTrigger` COLLAPSE imperativement dans `matches` (doctrine #149, comme
    `BarbedOvipositor` / `SwornProtector` / `MasterAnnihilator`) ; `CreateBehaviour` est un ARBRE
    DSL (feuille `AddBondEffect` au-dessus de l'Operation `AddEffectOperation`)."""
    event_id = int(EventTriggerType.Attack)                       # `On(9)`
    TRIGGERED_ABILITY_ID = _NEUROPARASITE_TRIGGERED               # 1183

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` -- le porteur est l'attaquant. Le port n'a qu'un canal d'acteur
        # (`ev.actor_id`) pour les slots `Actor@0x40` et `Caster@0x48`, qui coincident sur le
        # vecteur d'attaque (`finish_attack_triggers` construit l'event avec l'ATTAQUANT).
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        # `NOT (get_OwnerIsActor & get_OwnerIsTarget)` -- exclut l'AUTO-frappe. Ecrit en deux
        # conjoints separes pour rester le calque du natif ; le premier est deja vrai ici (le port
        # ne distingue pas Actor de Caster), donc c'est le second qui mord.
        owner_is_actor = int(ev.actor_id) == int(self.owner_id)
        owner_is_target = ev.target_id is not None and int(ev.target_id) == int(self.owner_id)
        if owner_is_actor and owner_is_target:
            return False
        if ev.target_id is None:
            return False
        tgt = state.get_entity(int(ev.target_id))
        if tgt is None:
            return False
        # `IsUnit(Target@0x60)` -- une TUILE / un objet de decor n'a pas de `UnitComponent`.
        if tgt.get_component(UnitComponent) is None:
            return False
        # `CurrentAttackDamageProfilesContain(0xd = Psychic, 0)` : c'est le SET des profils de
        # l'attaque, pas le seul profil d'arme (#202-C).
        if not _profiles_contain(ev, _PSYCHIC):
            return False
        # `NOT HasEffect(Target@0x60, 0x4c2, onlyActive: 0, 6)` -- la POSE ne se rejoue pas sur une
        # cible DEJA infectee ; c'est la montee en niveau (les deux `EffectTrigger` ci-dessous) qui
        # prend le relais. `onlyActive: 0` -> aucune lecture du flag `IsActive`, donc la simple
        # PRESENCE d'une instance non consommee suffit (foyer `_neuroparasite_instance`).
        return _neuroparasite_instance(state, int(ev.target_id)) is None

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        neuroparasite_bond_tree().execute(
            entities_from_state(state, self.owner_id, int(ev.target_id)), ectx)
        posed = [p for n, p in ectx.emitted if n == "AddBondEffect"]
        if not posed:
            return None
        return {"ability": NEUROPARASITE_ABILITY, "unit": int(self.owner_id),
                "target": int(ev.target_id), "effect": NEUROPARASITE_EFFECT}


class NeuroparasiteIncreaseLevelOnPsychicHit(EffectTrigger):
    """1er `Triggered()` de `NeuroparasiteEffect$$CreateHandleTriggerAbilitiesInternal` :
    `On(9) & GetDamageTakenTrigger()` -> `GetIncreaseLevelBehaviour()`, avec
    `$$GetDamageTakenTrigger = get_OwnerIsTarget & CurrentAttackDamageProfilesContain(0xd)`.

    ⚠ AUCUN gate sur l'auteur du coup : le natif ne verifie PAS que le frappeur est le Neurothrope
    bonde. N'IMPORTE QUELLE attaque psychique subie par la victime monte le parasite d'un cran --
    c'est la lecture du decompile, pas une simplification. (L'ADDITIF de degat, lui, est bien gate
    `AreEqual(BondedEntity, damageSource)` : les deux faces different, et c'est deliberement mirrore
    tel quel.)"""
    effect_type = NEUROPARASITE_EFFECT
    event_id = int(EventTriggerType.Attack)                       # `BaseEffect$$On(9)`
    TRIGGERED_ABILITY_ID = _NEUROPARASITE_TRIGGERED

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False                                          # `get_OwnerIsTarget`
        return _profiles_contain(ev, _PSYCHIC)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _increase_level(state, int(self.owner_id))


class NeuroparasiteIncreaseLevelOnPinned(EffectTrigger):
    """2e `Triggered()` de `NeuroparasiteEffect$$CreateHandleTriggerAbilitiesInternal` :
    `On(0x3d = 61 PreEffectAdded) & GetPreEffectAddedTrigger()` -> `GetIncreaseLevelBehaviour()`,
    avec `$$GetPreEffectAddedTrigger = get_OwnerIsTarget & TriggeringEffectIs(0x429 = 1065 Pinned)`.

    Le porteur du parasite qui se fait POSER un `Pinned` voit son parasite monter d'un cran. Le
    vecteur `pre_effect_added_triggers` fire AVANT les gates de l'operation (semantique
    « would have ») -- donc meme un Pinned finalement refuse (immunite, deja present) fait monter le
    parasite, exactement comme le natif."""
    effect_type = NEUROPARASITE_EFFECT
    event_id = int(EventTriggerType.PreEffectAdded)               # `BaseEffect$$On(0x3d)`
    TRIGGERED_ABILITY_ID = _NEUROPARASITE_TRIGGERED

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False                                          # `get_OwnerIsTarget`
        # `TriggeringEffectIs(0x429)` = le canal `AbilityEntities+0x98`, renseigne par
        # `AddEffectOperation$$Execute` sur la POSE (asymetrie #306).
        return ev.triggering_effect is not None and int(ev.triggering_effect) == _PINNED

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _increase_level(state, int(self.owner_id))
