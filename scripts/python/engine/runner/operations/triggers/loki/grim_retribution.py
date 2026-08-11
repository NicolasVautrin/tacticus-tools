"""`1213 GrimRetribution_CounterAttack` — la RIPOSTE de `darkaHellblaster` (Sarquael), portee par un
EFFET de la famille `IdunBattle.Entities.Effects.CounterAttackEffect`.

i2 : « During each enemy turn, if there is no enemy adjacent to Sarquael, he shoots back at the first
enemy within range that attacked him or a friendly adjacent Dark Angel. This shot counts as Overwatch
and deals 1x 2183-2619 Plasma Damage. »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) — decompile = verite
================================================================================================
Chaine COMPLETE (chaque maillon LU, aucun deduit du nom) :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.GrimRetributionAbility
        : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility    (classes.tsv)
    IdunBattle.Entities.Effects.Loki.GrimRetribution_CounterAttackEffect
        : IdunBattle.Entities.Effects.CounterAttackEffect
        : IdunBattle.Entities.Effects.PlayerTurnEffect
        : IdunBattle.Entities.Effects.BaseEffect                        (classes.tsv)

## 0. LE RECENSEMENT — par le bloc `methodPointers`, jamais par grep de nom

`GrimRetributionAbility` declare **DEUX** entrees : un `.ctor` dont le corps est le `ret` nu partage
avec `UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor`, et `GetEffectType`. Elle
n'override donc **NI `CreateTrigger` NI `CreateBehaviour`** — contrairement a `WireweaveNetAbility`,
qui, elle, override `CreateBehaviour` pour y ajouter un `If(NOT IsTurnOf(Owner)) -> ActivateEffect`.
Ecrire ici l'equivalent de ce `If` aurait ete une recopie du jumeau de forme, et elle aurait ARME la
riposte un tour trop tot.

`GrimRetribution_CounterAttackEffect` declare **SIX** entrees, dont **DEUX corps propres** :

    [ .ctor(PROPRE) · GetCounterAttackTargets(= WireweaveNet) · GetCounterAttackTrigger(= UnwaveringSentinel)
      · GetCounterAttackCondition(PROPRE) · GetCounterAttackBehaviour(= WireweaveNet)
      · GetDamage(= WireweaveNet) ]

L'ordre des six slots n'est pas suppose : il est ETABLI en confrontant les blocs des TROIS membres
portes de la famille, ou chaque corps partage par ICF tombe a la position HOMOLOGUE de son jumeau.

## 1. LA POSE — `AOwnerEffectTriggeredAbility$$CreateTrigger` + `$$CreateBehaviour` (herites)

    CreateTrigger   = OnOwnerSpecificAbilityInit(this.Id@+0x10)          # a l'INIT de l'ability
    CreateBehaviour = If( CreateCondition@vtable+0x368,
                          AddEffect(GetEffectType(), AbilityState(Owner),
                                    source = Owner@<DSLSelectors+0x30>,
                                    targets = Owner@<DSLSelectors+0x30>, <duree ZEROEE>) )

`GrimRetributionAbility$$GetEffectType` = `return 0x4bd` = **1213 en `EffectType`** (type de retour
LU dans `frida/methods.tsv` : `IdunBattle.Entities.Enum.EffectType`). En `TriggeredAbilityType` le
meme 1213 nomme `FieldsOfFire` — la qualification n'est pas decorative.

Port : `factory.ABILITY_INIT_OWNER_EFFECTS["GrimRetribution"] = ["GrimRetribution_CounterAttack"]`,
meme mecanisme que `WireweaveNet`. Le seed est INDISPENSABLE : l'effet est inactif pendant le tour de
son porteur, donc absent du canal `decisionView` par DEFAUT (actifs seuls).

## 2. LA FENETRE D'ARMEMENT — `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal`, branche freq 1

`.ctor` (litteraux LUS a l'assembleur, cf. `entities/effects/loki/counter_attack.py`) :
`turnsEnabled = 1`, `activationFrequency = 1`. La branche `== 1` est l'**INVERSE** de la branche
`== 2` qui porte `WireweaveNet` :

    On(0x12 = TurnStart_EffectActivation) & IsEnabledTurnType()  -> ActivateEffect(<Sel+0x38>)
    On(0x17 = TurnEnd)                    & IsEnabledTurnType()  -> DeactivateEffect(<Sel+0x38>)

et `PlayerTurnEffect$$IsEnabledTurnType` pour `turnsEnabled == 1` rend
`op_LogicalNot(<DSLTriggers+0x28>)` = `NOT IsTurnOf(Owner)`.

=> l'effet est ARME au DEBUT de CHAQUE tour ennemi et DESARME a sa FIN : **une riposte par tour
ennemi**, la ou `WireweaveNet` n'en autorise qu'une par CYCLE. C'est litteralement le « During each
enemy turn » de l'i2.

Le TROISIEME `Triggered()` de la meme methode (`On(0x2e = UnitResurrected) & OwnerIsTarget ->
ActivateEffect`) est gate par un virtuel booleen (`vtable +0x728`) dont l'implementation sur cette
chaine est un stub `return 0` -> **non bati**, comme pour `WireweaveNet`.

## 3. LA RIPOSTE — `CounterAttackEffect$$CreateTargetTrigger` / `$$CreateTargetTriggerBehaviour`

    CreateTargetTrigger =
          GetCounterAttackTrigger()              # vtable +0x778
        & <DSLTriggers+0x20>                     # conjoint SINGLETON non qualifie (cf. RESIDUS)
        & GetCounterAttackCondition()            # vtable +0x788
        & AreEnemies(Caster@<Sel+0x48>, Owner@<Sel+0x30>, 0)
        & IsAlive(Caster@<Sel+0x48>)

    GrimRetribution_CounterAttackEffect$$GetCounterAttackTrigger    # corps PARTAGE avec UnwaveringSentinel
        = On(0x9 = Attack, true)

⚠ **`On(Attack)`, PAS `On(PreUnitAbility)`.** `0x9 = 9 = Attack` (VERIFIE contre `frida/enums.tsv`,
pas deduit : `0xb = 11 = UnitAbility`, `0x2a = 42 = PreUnitAbility`). La riposte part donc APRES que
l'attaque adverse s'est executee — l'inverse exact de `WireweaveNet`, dont le `On(PreUnitAbility)`
est ce qui lui permet d'annuler le coup de l'attaquant s'il le tue. Ici l'i2 dit « he shoots back at
the first enemy ... **that attacked him** », au passe : le coup adverse a deja porte.

    GrimRetribution_CounterAttackEffect$$GetCounterAttackCondition   # PROPRE -- surcharges tranchees
                                                                     # par l'ADRESSE de la cible du call
        =   NOT HasAdjacentEnemies( unit = Owner@<Sel+0x30>, unitTile = Tiles(Owner),
                                    includeObjects = false, includeSteppables = false )
          & (   get_OwnerOrOwnerTileIsTarget
              | Contains( list     = UnitsFromFaction( AdjacentFriends(Owner, unique: true, Any),
                                                       UnitFaction.DarkAngels = 0xa, Any ),
                          elements = Units(Target@<Sel+0x60>, unique: true, OnlyTargetable) ) )
          & IsInAttackRange( rangedUnit = Owner@<Sel+0x30>, target = Caster@<Sel+0x48>,
                             OnlyAliveAndTargetable )

Les trois surcharges ambigues sont tranchees par l'ADRESSE REELLE de la cible du `call` (decodage
`E8 rel32`), jamais par le pseudo-C : `AdjacentFriends` = la surcharge `(unit, unique, selectionType)`
(et NON `(unit, unitTile, unique)`), `UnitsFromFaction` = la surcharge `faction: UnitFaction` (et NON
`factionId: String`), `Units` = la surcharge `(entities, unique, selectionType)` (et NON `onlyAlive`).
Les trois `selectionType` (`Any`, `Any`, `OnlyTargetable`) et les deux `unique` sont relus aux
octets (`xor r9d,r9d` / `mov r9d,2` / `mov r8b,1`).

⚠ **`HasAdjacentEnemies` compte `>= 1`, pas `> 1`** : la CLASSE allouee par
`IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies` (`DAT_1833d73e0`) est celle des deux
surcharges de `DSLTriggers$$AmountIsEqualOrGreater` ; `DSLTriggers$$AmountIsGreater` (STRICT) alloue
une classe DIFFERENTE (`DAT_1833d7670`). Le nom `AmountIsGreaterAbilityTrigger` que ghidra affiche
pour le ctor ET pour son `ShouldTrigger` est un mislabel ICF. C'est le foyer partage
`entities/triggers.has_adjacent_enemies` (#939) qui porte ce fait ; ce module le CONSOMME.

    GrimRetribution_CounterAttackEffect$$GetCounterAttackTargets     # corps PARTAGE avec WireweaveNet
        = <DSLSelectors+0x48>                                        # Caster

    CreateTargetTriggerBehaviour =
          GetCounterAttackBehaviour(effect)      # vtable +0x748
        & DeactivateEffect(effect)               # gate vtable +0x738 = stub `return 1` -> TOUJOURS

## 4. LE DEGAT — `CounterAttackEffect$$AttackDamage`

    GrimRetribution_CounterAttackEffect$$GetCounterAttackBehaviour   # corps PARTAGE avec WireweaveNet
        = CounterAttackEffect$$AttackDamage( effect,
                                             damageProfile = GetDamageProfile(config@+0x60),
                                             hits = GetNumberConstant(config@+0x60,
                                                        AbilityConstantType.nrOfHits = 0x2f) )

    CounterAttackEffect$$AttackDamage =
        DSLBehaviors.AttackWithAttackDamage( caster  = Owner@<Sel+0x30>,
                                             targets = GetCounterAttackTargets(),   # = Caster
                                             amount  = GetDamage(effect),
                                             damageProfile, hits,
                                             abilityOrEffect = <this.SourceAbility>,
                                             options = null,
                                             selectionType = OnlyTargetable )

    GrimRetribution_CounterAttackEffect$$GetDamage                   # corps PARTAGE avec WireweaveNet
        = BaseEffect$$GetMinMaxDamage(isPrediction: false)

gameconfig `GrimRetribution` : `attackRangeType = Ranged`, `constants = {damageProfile: "Plasma",
nrOfHits: "1"}`, `variables = {minDmg[65], maxDmg[65]}` — niveau 65 : 2183-2619. `GrimRetribution`
est le PASSIF de `darkaHellblaster` (`unit_map kit`) -> `level_slot="passive"`.

================================================================================================
RESIDUS EXPLICITES
================================================================================================
 * `<DSLTriggers+0x20>` : noeud-trigger SINGLETON du factory, non qualifie et NON porte — MEME residu
   que `wireweave_net.py` et `martial_superiority.py` (il ne recoit que `factory@+0x10`, donc il ne
   peut porter qu'une condition GLOBALE ; la mesure live tranche qu'elle ne bloque pas).
 * Le natif lit la cible de la riposte dans le slot **`Caster`** (`<DSLSelectors+0x48>`), pas `Actor` ;
   sur le vecteur `On(Attack)` les deux slots designent la MEME entite (l'attaquant), et c'est elle
   que `TriggerEvent.actor_id` porte. MEME residu que `wireweave_net.py`.
 * `get_OwnerOrOwnerTileIsTarget` = `AreEqual(Target, Owner) | AreEqual(Target, Tiles(Owner))` : le
   port n'a qu'UNE cible d'evenement (une entite) -> la 2e branche est structurellement couverte par
   la 1re. MEME residu que `wireweave_net.py`.
 * « **This shot counts as Overwatch** » (i2) n'a **AUCUN correspondant LU** dans les six corps de la
   classe ni dans `CounterAttackEffect$$AttackDamage` : aucun de ces corps ne pose de marqueur
   d'overwatch, et `AttackWithAttackDamage` recoit `source = AbilityOrEffect{TriggeredAbility = 1177}`,
   pas un id d'overwatch. C'est donc soit un etage NON LU (cote consommateur du `source`), soit de la
   prose i2. Ecrit comme NON RESOLU plutot que devine — un `is_overwatch` invente ici armerait
   `LionHelm_ExtraDmg` branche B (cf. `entities/effects/loki/dark_angels_passives.py`) sur une
   hypothese. Residu **#946-r1**.
 * `AttackWithAttackDamage` recoit `source = AbilityOrEffect{TriggeredAbility = 1177}` ; le canal
   `ability_type` du port est keye sur l'espace `ActiveAbilityType` -> non threade (MEME choix que
   `WireweaveNet`, `MartialSuperiority` et `MartialApotheosis`).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Actor, Owner, Target
from .....entities.selectors.units import (AdjacentFriends, Tiles, Units,
                                           UnitsFromFaction)
from .....entities.triggers import Contains, has_adjacent_enemies
from .....entities.unit_faction import UnitFaction
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....components import OwnerComponent, UnitComponent
from ....state import State
from ..base import EffectTrigger, TriggerEvent, _in_attack_range
from . import counter_attack as _ca     # forme B : le socle PARTAGE de la famille (#946)

GRIM_RETRIBUTION_COUNTER_ATTACK = int(EffectType.GrimRetribution_CounterAttack)   # 0x4bd = 1213
GRIM_RETRIBUTION = "GrimRetribution"    # nom gameconfig de l'ability SOURCE (passif de `darkaHellblaster`)
_PROFILE = "Plasma"                     # `GetDamageProfile(cfg)` -> constants.damageProfile
#: Les trois `UnitSelectionType` du `GetCounterAttackCondition`, relus aux octets (cf. l'en-tete).
_SEL_ANY = int(UnitSelectionType.Any)                        # 0 -- AdjacentFriends, UnitsFromFaction
_SEL_TARGETABLE = int(UnitSelectionType.OnlyTargetable)      # 2 -- Units(Target)


def dark_angel_friend_is_target_tree():
    """Le SECOND disjoint de `GetCounterAttackCondition`, noeud par noeud (doctrine #149 :
    l'artefact natif est un arbre de selecteurs, donc le port est un arbre) :

        Contains( list     = UnitsFromFaction( AdjacentFriends(Owner@+0x30, unique: true, Any),
                                               UnitFaction.DarkAngels = 0xa, Any ),
                  elements = Units(Target@<Sel+0x60>, unique: true, OnlyTargetable) )

    `reference=Owner()` est passe EXPLICITEMENT a `AdjacentFriends` (la reference d'equipe du
    `Friends` natif EST le centre), et `UnitFaction.DarkAngels.name` — pas l'ordinal — parce que le
    natif compare le `FactionId` gameconfig au NOM de la valeur d'enum (`System.Enum.ToString`
    puis `String.Equals` sur `FactionComponent+0x30`). MEME convention que
    `entities/effects/loki/deathwing.adjacent_dark_angels_friends_selector`.

    ⚠ Les `selectionType` sont `Any` aux DEUX etages du selecteur d'amis, et `OnlyTargetable` sur
    `Units(Target)` : trois litteraux DIFFERENTS dans le meme corps, relus aux octets. Recopier le
    `OnlyAliveAndTargetable` du selecteur voisin (`deathwing`) aurait ecarte des Dark Angels que le
    natif compte."""
    return Contains(UnitsFromFaction(AdjacentFriends(Owner(), Const(1), Owner(), _SEL_ANY),
                                     UnitFaction.DarkAngels.name, _SEL_ANY),
                    Units(Target(), selection_type=_SEL_TARGETABLE))


def no_adjacent_enemy_tree():
    """Le PREMIER conjoint : `NOT HasAdjacentEnemies(Owner@+0x30, Tiles(Owner), false, false)`.

    Passe par le foyer PARTAGE `entities/triggers.has_adjacent_enemies` (#939), qui porte le corps
    natif entier — y compris le fait, non deductible du nom, que le seuil est `>= 1` (cf. l'en-tete).
    Les DEUX booleens sont `false` (relus aux octets : `xor r8d,r8d` pour `includeObjects`, low byte
    efface pour `includeSteppables`), donc les deux `UnitsWithoutTrait` du corps natif sont POSES."""
    return has_adjacent_enemies(Owner(), Tiles(Owner()),
                                include_objects=False, include_steppables=False)


def grim_retribution_tree():
    """UNE feuille `AttackWithAttackDamage` sur l'ATTAQUANT — mirror de
    `CounterAttackEffect$$AttackDamage` : `caster = Owner@<Sel+0x30>` (Sarquael),
    `targets = GetCounterAttackTargets() = <Sel+0x48>` (le Caster de l'ability declenchante, porte
    ici par `Actor()` — cf. RESIDUS), `amount = GetDamage() = GetMinMaxDamage(minDmg/maxDmg[level])`,
    `damageProfile = GetDamageProfile(cfg) = "Plasma"`, `hits = GetNumberConstant(cfg,
    AbilityConstantType.nrOfHits) = 1`.

    `attackRangeType = Ranged` au gameconfig -> `is_melee=False`. ⚠ C'est un ECART avec
    `wireweave_net_tree` (`is_melee=True`), et il n'est pas cosmetique : il choisit le profil d'arme
    et les modificateurs positionnels du pipeline de degat.

    La config est celle de l'ability SOURCE de l'effet, montee en PASSIF sur `darkaHellblaster` ->
    `level_slot="passive"`. `multi=False` = collapse MONO-CIBLE (le slot `Caster` ne porte qu'UNE
    entite)."""
    return AttackWithAttackDamage(Actor(), GRIM_RETRIBUTION, _PROFILE,
                                  is_melee=False, level_slot="passive")


class GrimRetributionCounterAttack(EffectTrigger):
    """`CounterAttackEffect$$CreateTargetTrigger` + `$$CreateTargetTriggerBehaviour` pour
    `GrimRetribution_CounterAttackEffect` — la RIPOSTE elle-meme (cf. §3/§4 de l'en-tete)."""
    event_id = EventTriggerType.Attack          # `GetCounterAttackTrigger` = On(0x9 = Attack, true)
    effect_type = GRIM_RETRIBUTION_COUNTER_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # (a) gate `EffectComponent.IsActive @+0x5c` — premier test d'`EvaluateEffectTriggerTargets`,
        #     AVANT toute evaluation du trigger de cible. Ici il ne porte PAS un « first time »
        #     perpetuel mais le « une riposte par tour ennemi » : le behaviour desactive l'instance,
        #     et `GrimRetributionActivateOnEnemyTurnStart` la re-arme au tour ennemi SUIVANT.
        if not _ca.flag_is_set(state, self.owner_id, GRIM_RETRIBUTION_COUNTER_ATTACK):
            return False
        # (b) REPLI de la fenetre d'armement (`NOT IsTurnOf(Owner)`), exactement comme
        #     `wireweave_net.py` : le trigger de cible natif ne porte PAS ce conjoint, la fenetre y
        #     est portee UNIQUEMENT par le flag que les deux `Triggered()` du §2 ecrivent aux
        #     boundaries de tour. L'invariant natif est « actif => pas le tour du porteur » — le
        #     repli est EXACT, et indispensable sur un etat SEEDE mi-tour (le seed materialise
        #     l'instance ACTIVE sans jamais avoir vu de `On(0x12)`), regime de tous les tests.
        if _ca.is_turn_of_owner(state, self.owner_id, ev) is not False:
            return False
        attacker = ev.actor_id
        if attacker is None or int(attacker) == int(self.owner_id):
            return False
        ow = state.get_entity(self.owner_id)
        att = state.get_entity(attacker)
        if ow is None or att is None:
            return False
        # (c) `AreEnemies(Caster@<Sel+0x48>, Owner@<Sel+0x30>, 0)`.
        ac = att.get_component(OwnerComponent)
        oc = ow.get_component(OwnerComponent)
        if ac is None or oc is None or ac.team == oc.team:
            return False
        # (d) `IsAlive(Caster@<Sel+0x48>)` — ET leg de re-validation du drain (`RunPhase`/`VerifyDeaths`
        #     re-evaluent chaque item contre l'etat courant : un attaquant tue entre l'enfilement et
        #     le drain ne matche plus).
        auc = att.get_component(UnitComponent)
        if auc is not None and not auc.alive:
            return False
        # (e) `GetCounterAttackCondition`, conjoint par conjoint et DANS L'ORDRE NATIF. Les trois
        #     conjoints partagent le meme `AbilityEntities` : `entities_from_state` pose
        #     `caster = owner = le porteur` et `actor = l'attaquant`, et c'est `Target()` qui designe
        #     la cible de l'attaque declenchante (`<Sel+0x60>`).
        ents = entities_from_state(state, int(self.owner_id), actor_id=int(attacker),
                                   target_id=(int(ev.target_id) if ev.target_id is not None else None))
        #     (e1) `NOT HasAdjacentEnemies(Owner, Tiles(Owner), false, false)`.
        if no_adjacent_enemy_tree().should_trigger(ents):
            return False
        #     (e2) `get_OwnerOrOwnerTileIsTarget | Contains(<Dark Angels adjacents>, Units(Target))`.
        #          La 1re branche se lit sur l'EVENEMENT (le port n'a qu'une cible-entite, cf.
        #          RESIDUS) ; la 2e est l'arbre de selecteurs.
        owner_is_target = (ev.target_id is not None and int(ev.target_id) == int(self.owner_id))
        if not owner_is_target and not dark_angel_friend_is_target_tree().should_trigger(ents):
            return False
        #     (e3) `IsInAttackRange(Owner, Caster, OnlyAliveAndTargetable)` — le foyer UNIQUE du
        #          predicat (`triggers/base._in_attack_range`), qui compose portee d'arme + clamp
        #          `ForcedInMelee` + distance. Le 3e argument natif (`unitSelectionType`) n'est pas
        #          porte : `IsInAttackRangeAbilityTrigger$$ShouldTrigger` ne le lit jamais (meme
        #          residu que `_IsInAttackRange` de `light_im_up.py`).
        return _in_attack_range(state, int(self.owner_id), int(attacker))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`CreateTargetTriggerBehaviour` = `GetCounterAttackBehaviour(effect) & DeactivateEffect(effect)`,
        dans CET ordre (`AbilityBehaviour$$op_BitwiseAnd`, gauche puis droite)."""
        if state.rng is None:                          # l'attaque consomme le RNG (rolls/crit/block)
            return None
        entities = entities_from_state(state, self.owner_id, actor_id=int(ev.actor_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        grim_retribution_tree().execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        atk = atks[0] if atks else None
        deactivated = _ca.set_active(state, self.owner_id, GRIM_RETRIBUTION_COUNTER_ATTACK, False)
        return {"effect": "GrimRetribution_CounterAttack", "caster": int(self.owner_id),
                "target": (atk.get("target") if atk else None),
                "attack": (atk.get("attack") if atk else None),
                "deactivated": deactivated, "dsl": True}


class GrimRetributionActivateOnEnemyTurnStart(EffectTrigger):
    """1er `Triggered()` de la branche `ActivationFrequency == 1` de
    `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal` :

        On(0x12 = TurnStart_EffectActivation) & IsEnabledTurnType() -> ActivateEffect(<Sel+0x38>)

    avec `IsEnabledTurnType()` = `NOT IsTurnOf(Owner)` pour `turnsEnabled == 1`. ARME la riposte au
    debut de CHAQUE tour ennemi — c'est CE `Triggered()` qui porte le « During **each** enemy turn »,
    et c'est lui qui distingue la cadence de celle de `WireweaveNet` (freq 2, ou le meme evenement
    DESARME au lieu d'armer)."""
    event_id = EventTriggerType.TurnStart_EffectActivation
    effect_type = GRIM_RETRIBUTION_COUNTER_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return _ca.is_turn_of_owner(state, self.owner_id, ev) is False

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _ca.set_active(state, self.owner_id, GRIM_RETRIBUTION_COUNTER_ATTACK, True):
            return None                                # deja actif -> aucune ecriture (no-op)
        return {"effect": "GrimRetribution_CounterAttack", "owner": int(self.owner_id),
                "activated": "turn_start_of_enemy"}


class GrimRetributionDeactivateOnEnemyTurnEnd(EffectTrigger):
    """2e `Triggered()` de la meme branche :

        On(0x17 = TurnEnd) & IsEnabledTurnType() -> DeactivateEffect(<Sel+0x38>)

    DESARME la riposte a la fin de chaque tour ennemi. Observationnellement redondant avec le repli
    `NOT IsTurnOf(Owner)` du `matches` de la riposte, mais porte quand meme : 1 `Triggered()` natif
    = 1 artefact offline, et c'est LUI qui explique pourquoi 1213 est absent du canal `decisionView`
    par DEFAUT pendant le tour de Sarquael.

    `EvaluateEffectTriggerEffectAbilities` (la voie de ces `Triggered()`) n'applique AUCUN gate
    `IsActive`, contrairement a `EvaluateEffectTriggerTargets` — c'est ce qui permet de re-activer
    une instance desactivee ; le port fait pareil (`collect_effect_triggers` ne filtre pas sur
    `e.active`)."""
    event_id = EventTriggerType.TurnEnd
    effect_type = GRIM_RETRIBUTION_COUNTER_ATTACK

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return _ca.is_turn_of_owner(state, self.owner_id, ev) is False

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _ca.set_active(state, self.owner_id, GRIM_RETRIBUTION_COUNTER_ATTACK, False):
            return None                                # gate natif « deja inactif -> no-op »
        return {"effect": "GrimRetribution_CounterAttack", "owner": int(self.owner_id),
                "deactivated": "turn_end_of_enemy"}
