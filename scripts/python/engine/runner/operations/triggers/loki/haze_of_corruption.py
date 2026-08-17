"""`HazeOfCorruption` (passif de `deathBlightlord` << Maladus >>, PassiveAbilityType /
TriggeredAbilityType 1076) -- volet TARGET-FINDER : le sous-trigger qui, A L'ENTREE de CHAQUE ability
du porteur, TIRE au hasard jusqu'a 2 relais de transfert de degat et les BONDE.

i2 : « When Maladus attacks and defeats a unit, any leftover Damage and an additional 1x 1019 Toxic
Damage is dealt to a random enemy adjacent to both Maladus and his initial target. If this unit is
also defeated, this ability triggers again, dealing Damage to an additional unit adjacent to both
Maladus and his initial target. »

Le « random » est tire AVANT l'attaque, pas au moment du kill : c'est ce qui rend ce volet
OBSERVABLE meme quand rien ne meurt -- il consomme du RNG a chaque attaque.

================================================================================================
RE (decompile ghidra, build `gqfc5mff6c`) -- case-207
================================================================================================

## `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateTrigger`

    On(0x2a = PreUnitAbility, 1) & get_OwnerIsCaster

AUCUN autre terme : ni `IsNormalAttack`, ni `AbilityHasAttackType`, ni `AreEnemies`. Le volet se
declenche donc pour N'IMPORTE QUELLE ability du porteur (attaque normale, 1042 FlailSwing, ...).

## `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`

    sel   = Damageable( AdjacentEnemies(Self@0x148, 1, 3) & AdjacentFriends(Target@0x178, 1, 3) )
    pick  = PickRandomly(sel, 2, allowRepeat = 0, maxRepeat = 0x7fffffff, ignoreForcedTargets = false)
    units = TargetsSelector.SelectAllUnits(pick, entities, 3)      # <<-- LES TIRAGES ONT LIEU ICI
    beh   = Nothing()
    if Count(units) > 0 : beh += AddBondEffect(0x435, AbilityStateReference,
                                               Target@0x178, Get(units, 0), Self@0x148, One@0xc0)
    if Count(units) > 1 : beh += AddBondEffect(0x435, AbilityStateReference,
                                               Get(units, 0), Get(units, 1), Self@0x148, One@0xc0)
    beh  += SetPersistentData( AbilityOrEffect(this.Id), Self@0x148, Get(<cle statique>),
                               EntityId(Target@0x178) )

`SelectAllUnits` est appele **DANS `CreateBehaviour`** (la FORME de l'arbre depend du cardinal
resolu) : le tirage est donc paye a CHAQUE declenchement du trigger, avant tout coup.

Chaines lues, verbatim :
  * `IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies(X, p3, p4)` (surcharge 4-args) =
    `Enemies(reference = X, Units(AdjacentTiles(X), p3, p4) op_Subtraction X, p4)` ;
  * `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(X, p3, p4)` = idem avec `Friends`.
    **La reference d'equipe est X lui-meme** -> `AdjacentFriends(Target)` = les allies DE LA CIBLE,
    c'est-a-dire les ENNEMIS du caster ici. Cf. le meme collapse deja documente sur
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetSurroundingUnits` ;
  * `IdunBattle.DSL.TargetsSelector$$op_BitwiseAnd` = INTERSECTION (le champ mode `+0x28` vaut 0 ;
    `op_Addition` construit la MEME classe avec 1) ;
  * `IdunBattleLogic.Entities.DSLSelectors$$Damageable(x)` = `UnitsWithoutTrait(x, 0x40e, 3)` ;
  * `IdunBattleLogic.Entities.DSLSelectors$$PickRandomly(source, amount, allowRepeat, maxRepeat,
    ignoreForcedTargets)` -> `IdunBattle.Entities.Selectors.PickRandomAmountSelector` : `min(len(pool),
    amount)` tirages, bornes decroissantes, **meme quand le pool tient dans `amount`** (loi case-130).

================================================================================================
CE QUE CA CORRIGE (case-207) -- 2 tirages `genrand` manquants par attaque
================================================================================================
Montage `deathBlightlord` melee nue sur `astraCreed` (porteur de `SwornProtector`), board MC1_67,
seed 777 : le natif consommait **5** `genrand_int32`, le port **3** (les 3 coups d'arme). Les 3
valeurs LIVE valent exactement `raw[2], raw[3], raw[4]` de la MEME cellule `[890, 1934]` que le
port -> cellule et ordre JUSTES, deux tirages manquants EN AMONT.

Les deux tirages sont DEUX declenchements de CE trigger, un par emission de `On(0x2a = PreUnitAbility)` :
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` re-entre par
`$$ExecuteForReplacedTarget` quand `SwornProtector` a fait entrer Kell sur la tuile visee (#120bis,
deja porte dans `operations/active_ability.py`) -- la re-entree re-emet `On(0x2a = PreUnitAbility)`.

  * emission 1, Target = Creed  : pool = {Kell}  -> 1 tirage `NextInternal(0, 1)` + 1 bond ;
  * emission 2, Target = Kell   : pool = {Creed} -> 1 tirage `NextInternal(0, 1)` + 1 bond.

MESURE LIVE (`probe_207_haze_target_finder.py --dump-events`, seed 777) -- les deux bonds sont
visibles dans le flux d'evenements natif, AVANT le premier coup d'arme :
    Effect_Id 100 : BondEffect_BondedId 79, Effect_SourceId 77, Effect_SourceTriggeredAbility 1076
    Effect_Id 101 : BondEffect_BondedId 79, Effect_SourceId 94, Effect_SourceTriggeredAbility 1076
`Effect_SourceId` = `Target@0x178` de l'emission (77 = Creed, puis 94 = Kell) ; `Effect_RemainingTurns`
= 1 aux deux.

CONTROLE 1v1 (`--target astraBullgryn`, aucun allie adjacent a la cible) : pool = {} sur l'unique
emission -> **0 tirage, 0 bond**, natif 3 == port 3, bit-exact. C'est ce controle qui REFUTE la
lecture UNION d'`op_BitwiseAnd` (elle aurait donne 1 tirage) et qui exclut un modele « 2 tirages a
chaque attaque du porteur ».

================================================================================================
CHARGE UTILE -- l'effet 0x435 = 1077 `HazeOfCorruption_DamageTransfer` (case-209)
================================================================================================
Le bond pose ci-dessus est un `ABondEffect` : `IdunBattle.Entities.Effects.Loki.
HazeOfCorruption_DamageTransferEffect$$.ctor` = `ABondEffect..ctor(this, 1, 0,
Nullable<AbilityOrEffect>(0x434 = 1076 HazeOfCorruption), 0)`. Deux accesseurs le structurent :

  * `$$GetDamageSource`        = `EffectSource(Effect@0x150)`            -> la cible INITIALE ;
  * `ABondEffect$$BondedEntitySelector` = `BondedEntityFromEffect(Effect@0x150)` -> Maladus.

## `…HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger`

    ( OnDeath(1, 1) & ( TriggeringAbilityIs(AbilityOrEffect(0x435)) | AreEqual(Actor@0x158, bonded) ) )
    | On(0x2d = UnitRevived, 1)
    | On(0x34 = UnitFled,    1)
    ) & IsAlive(bonded) & AreEqual(Target@0x178, EffectSource(Effect@0x150))

Lecture : la MORT de la cible initiale (`AreEqual(Target, EffectSource)`) tuee PAR Maladus
(`Actor@0x158` = l'auteur du coup fatal) -- ou par un transfert 1077 anterieur, ce qui CHAINE le
relais suivant -- avec Maladus VIVANT. Les deux `On` supplementaires sont les voies de RETRAIT
(la cible ressuscite / fuit) : meme behaviour, mais `GetLeftOverDamages` y rend vide, donc seul le
`GetRemoveEffectBehaviour` s'applique.

## `…HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour`

    dmgs = GetLeftOverDamages(entities)
    beh  = Nothing() + GetRemoveEffectBehaviour()
    foreach d in dmgs:
        beh += AttackDamage( bonded, Owner@0x148,
                             Get(d.amount@+0x70), Direct(Nullable<DamageType>(d.type@+0x6c)),
                             One@0xc0, AbilityOrEffect(0x435), <options par defaut> )
    return Attack(bonded, Owner@0x148, beh, <options par defaut>)

`IdunBattleLogic.Entities.DSLBehaviors$$Attack` -> `IdunBattle.Entities.Behaviours.AttackBehaviour$$
.ctor(this, attacker@+0x50, target@+0x58, behaviour@+0x60, options)` : **l'attaquant est le BONDED
(Maladus), la cible est le porteur de l'effet (le relais)**. Idem pour chaque `AttackDamage`
(`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor` : `+0x50` caster, `+0x58` cible,
`+0x60` noeud de degat, `+0x80` nb de coups = `One`, `+0x88` profil, `+0x68` AbilityOrEffect).

## `…$$GetLeftOverDamages` / `$$GetLeftOverDamagesFromEntity`

    GetLeftOverDamagesFromEntity(e) = e.<composant>.LeftOverDamages (champ +0x90)

    GetLeftOverDamages(entities):
        dmgs = GetLeftOverDamagesFromEntity(Target@0x178 du contexte)   # entities[+0x10]
        if dmgs.Count > 0 : return dmgs
        node = GetPersistentData(AbilityOrEffect(0x434), bonded, <cle statique>)   # la cible INITIALE
        if node == null : return dmgs
        ent = world.GetEntity(node.Evaluate(entities))
        if ent == null or !ent.IsUnit() : return dmgs
        return GetLeftOverDamagesFromEntity(ent)

C'est la RELECTURE de la memoire posee par `SetPersistentData` du target-finder : quand le trigger
part sur le RELAIS (chaine), le contexte n'a plus les leftovers -- on retourne les lire sur la cible
INITIALE. La liste est celle qu'ecrit `IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit`
(meme champ +0x90 que lit `ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits`, cf.
`abilities/behaviours/combat.py`).

RESIDUS EXPLICITES
==================
 * `SetPersistentData(AbilityOrEffect(Id), Self, Get(<cle>), EntityId(Target))` : le port n'a pas de
   couche « persistent data » d'ability -> no-op documente (c'est la memoire de la cible INITIALE que
   relit `GetLeftOverDamages` ci-dessus).
 * `Damageable` = `UnitsWithoutTrait(0x40e, 3)` cote natif ; le port collapse en « vivant et PV > 0 »
   (collapse PRE-EXISTANT du noeud `entities/selectors/units.py::Damageable`, inchange ici).
 * ORDRE du pool quand `len(pool) > 2` : residu #215 standing (le natif tire dans l'ordre du selecteur
   source ; le port rend l'ordre `AdjacentTiles` natif via `Board.neighbours_native`, ce qui est le
   bon ordre pour le terme GAUCHE de l'intersection). La CONSOMMATION, elle, est exacte a tout
   cardinal.
 * Branches `UnitResurrected` / `UnitRevived` : sans objet (ce trigger n'ecoute que `On(0x2a = PreUnitAbility)`).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddBondEffect
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import (
    AdjacentEnemies, AdjacentFriends, And, Damageable, UnitSet
)
from ..base import EffectTrigger, TriggeredAbility, TriggerEvent
from ....abilities.base import ability_attack_params
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import RemoveEffect
from ....abilities.loki.splash import _pick_randomly_n
from ....components import StatsComponent, UnitComponent
from ....components import UnitComponent
from ...damage import AttackDamageOperation
from ...left_over_damage import left_over_damages

HAZE_OF_CORRUPTION_ABILITY = "HazeOfCorruption"
# `AddBondEffect(0x435, ...)` -> EffectType 1077 `HazeOfCorruption_DamageTransfer`.
HAZE_DAMAGE_TRANSFER = int(EffectType.HazeOfCorruption_DamageTransfer)
HAZE_DAMAGE_TRANSFER_NAME = EffectType.HazeOfCorruption_DamageTransfer.name
_ON_PRE_UNIT_ABILITY = int(EventTriggerType.PreUnitAbility)     # 0x2b = 43
# `IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent(eventId, allowOverkill, allowShield)` -- RELU
# VERBATIM (case-haze-bonded) ; les deux enveloppes ne visent PAS le meme evenement :
#   `OnPreDeath(a, b)` -> `OnDeathEvent(**1** = PreUnitDeath, a, b)`   [HazeCorruption_BonusHitAbility]
#   `OnDeath(a, b)`    -> `OnDeathEvent(**0** = UnitDeath,    a, b)`   [le report 1077]
# et les deux drapeaux sont des GATES sur la CIBLE, ajoutes seulement quand ils valent ZERO :
#   `allowOverkill == 0` -> `NOT HasFlagAbilityTrigger(Target@0x178, 8 = Overkilled)`
#   `allowShield   == 0` -> `NOT CurrentShieldAmountFormula(Target@0x178, 0x1b)`
# `OnPreDeath(1, 0)` du coup bonus = aucun gate d'overkill, mais la cible ne doit porter AUCUN
# bouclier ; `OnDeath(1, 1)` du report = aucun des deux.
_ON_UNIT_DEATH = int(EventTriggerType.UnitDeath)                # 0
_ON_PRE_UNIT_DEATH = int(EventTriggerType.PreUnitDeath)         # 1
# `GetVariableForLevel(config, 8)` = `extraDmg` ; `GetDamageProfile(config)` = `damageProfile`
# (constante gameconfig de `HazeOfCorruption` = "Toxic", DamageProfileType 24 mesure live).
HAZE_EXTRA_DMG_KEY = "extraDmg"
HAZE_BONUS_PROFILE = "Toxic"
# `PickRandomly(sel, 2, 0, 0x7fffffff, false)` : le litteral d'amount, LU au call-site.
HAZE_PICK_AMOUNT = 2
# Duree du bond : struct `(Owner@0x148, One@0xc0)` passee a `AddBondEffect` -> `Effect_RemainingTurns`
# vaut **1** dans le flux d'evenements natif (mesure `probe_207_haze_target_finder.py`), donc une duree
# deja exprimee en TOURS (pas de `ConvertRoundsToTurns` a appliquer).
HAZE_BOND_TURNS = 1


def _triggering_ability_or_effect(state: State, ev: TriggerEvent):
    """Le champ `TriggeringAbility` (`AbilityEntities+0x98`) -- l'`AbilityOrEffect` DECLENCHEUR, celui
    que comparent `IdunBattleLogic.Entities.DSLTriggers$$TriggeringAbilityIs` **et**
    `IdunBattleLogic.Entities.DSLTriggers$$TriggeringEffectIs`. Les deux factories sont le MEME code
    (decompile lu : meme slot `DSLSelectors+0x90` + `DirectAbilitySelector(AbilityOrEffect(x))` + le
    meme ctor de trigger) et le lecteur unique en est
    `IdunBattleLogic.Entities.AbilityTypeSelector.TriggeringAbilitySelector$$Select`, qui lit
    `+0x98/+0xa0/+0xa8/+0xb0`. Il n'y a donc qu'UN champ natif, la ou le port a deux sources :

      * `ev.triggering_effect` -- renseigne par les vecteurs qui le portent explicitement
        (`On(PreEffectAdded)`, `On(DamageDealt)`) ;
      * `state.trigger_ability_type` -- le canal `+0x98` du port. Sur le vecteur MORT il est pose
        par `operations/damage.py::_verify_deaths` a partir du `killTrigger` de la file, mirror du
        bloc `AbilityEntities+0x98..+0xb4 = KillUnitOptions+0x04` qu'ecrit
        `IdunBattle.Operations.KillUnitOperation$$Execute` (#301) ; hors mort, il est pose par
        `triggers/dispatch/core.py::_publish_unit_triggered_ability` pour `On(0xd)`.

    ⚠ NE PAS LIRE `state.triggering_ability` ICI (#301) : ce canal-la mirror `CurrentAbility`
    (`+0x60`), que `KillUnitOperation$$Execute` laisse a ZERO sur ses cinq evenements -- un
    `Triggering*Is` branche dessus lirait un champ que le natif ne publie pas sur ce vecteur."""
    te = getattr(ev, "triggering_effect", None)
    if te is not None:
        return te
    # Acces DIRECT (meme raison qu'en #294) : le slot est declare dans `State.__slots__`. Un objet
    # qui ne l'a pas n'est pas un `State` -> ca doit LEVER, pas degrader en « pas de declencheur »,
    # qui est precisement le mode de panne permissif que ce gate anti-chaine doit empecher.
    return state.trigger_ability_type

# `Damageable( AdjacentEnemies(Self@0x148, 1, 3) & AdjacentFriends(Target@0x178, 1, 3) )` -- arbre DSL
# VERBATIM. `Caster()` = `Self@0x148` (trigger : Owner == Caster, c'est le gate `get_OwnerIsCaster`) ;
# la reference d'equipe du 2e terme est le TARGET lui-meme (surcharge 4-args), d'ou `reference=Target()`.
HAZE_TARGET_POOL = Damageable(And(AdjacentEnemies(Caster(), Const(1)),
                                  AdjacentFriends(Target(), Const(1), reference=Target())))


class HazeOfCorruptionTargetFinderAbility(TriggeredAbility):
    """`HazeOfCorruption_TargetFinderAbility` -- `On(PreUnitAbility = 0x2a) & get_OwnerIsCaster`.

    Tire (jusqu'a) 2 relais de transfert dans `Damageable(AdjacentEnemies(Self) & AdjacentFriends(
    Target))` et pose les bonds 1077 correspondants. Le TIRAGE est l'observable : `min(len(pool), 2)`
    `genrand_int32`, a l'entree de CHAQUE ability du porteur (cf. l'en-tete du module)."""
    event_id = _ON_PRE_UNIT_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` -- SEUL terme du `CreateTrigger` (aucun gate d'attaque, aucun gate de
        # camp, aucun gate sur le cardinal du pool : un pool VIDE donne un behaviour a 0 tirage,
        # pas un trigger qui ne fire pas).
        return ev.actor_id == self.owner_id

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        pool = list(HAZE_TARGET_POOL.evaluate(entities) or [])
        # `TargetsSelector.SelectAllUnits(PickRandomly(pool, 2, allowRepeat=0, maxRepeat=0x7fffffff))`
        # -> `min(len(pool), 2)` tirages, bornes decroissantes (loi case-130, foyer partage).
        picked = _pick_randomly_n(state, pool, HAZE_PICK_AMOUNT)
        # `if Count > 0 : AddBondEffect(0x435, absRef, Target@0x178, Get(units,0), Self@0x148, One)`
        # `if Count > 1 : AddBondEffect(0x435, absRef, Get(units,0), Get(units,1), Self@0x148, One)`
        # `SetPersistentData(...)` = no-op documente (pas de couche persistent-data cote port).
        ectx = ExecutionContext(state=state, rng=state.rng)
        for src_node, tgt_unit in self._bond_pairs(picked):
            # 5e argument natif = `Self@0x148` (le PORTEUR du passif) -- IDENTIQUE sur les DEUX
            # `AddBondEffect` : les deux bonds de la chaine sont bondes au MEME Maladus, seule la
            # SOURCE change (`Target@0x178` puis `Get(units,0)`). C'est cette entite que compare
            # `AreEqual(Actor@0x158, bonded)` et que teste `IsAlive(bonded)` cote
            # `HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger`, et c'est elle
            # l'ATTAQUANT du `Attack(bonded, Owner@0x148, beh)` du report.
            AddBondEffect(HAZE_DAMAGE_TRANSFER, HAZE_DAMAGE_TRANSFER_NAME, src_node,
                          UnitSet([tgt_unit]), duration_rounds=None,
                          duration_turns=HAZE_BOND_TURNS, bonded_ref=Caster()).execute(entities, ectx)
        bonds = [(p["source"], p["target"]) for n, p in ectx.emitted if n == "AddBondEffect"]
        return {"ability": HAZE_OF_CORRUPTION_ABILITY, "unit": self.owner_id,
                "target": ev.target_id, "pool": [u.get("id") for u in pool],
                "picked": [u.get("id") for u in picked], "bonds": bonds}

    @staticmethod
    def _bond_pairs(picked: list) -> list:
        """Les (source, cible) des deux `AddBondEffect` natifs, dans l'ORDRE d'emission :
        `(Target@0x178, units[0])` puis `(units[0], units[1])` -- une CHAINE, pas deux bonds paralleles
        (le 2e relais prend le relais du 1er quand celui-ci est defait a son tour)."""
        out = []
        if len(picked) > 0:
            out.append((Target(), picked[0]))
        if len(picked) > 1:
            out.append((UnitSet([picked[0]]), picked[1]))
        return out


class HazeCorruptionBonusHitAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HazeCorruption_BonusHitAbility` (case-209) --
    le coup TOXIC bonus que le porteur inflige a sa cible AU MOMENT ou elle tombe.

        CreateTrigger   = OnPreDeath(1, 0) & get_OwnerIsActor & IsDead(Target@0x178)
                          & NOT IsDead(Owner@0x148) & NOT TriggeringEffectIs(0x435)
        CreateBehaviour = AttackDamage( Owner@0x148, Target@0x178,
                                        Get(GetVariableForLevel(config, 8 = extraDmg)),
                                        Direct(GetDamageProfile(config)),      # Toxic
                                        Get(GetNumberConstant(config, 0x2f)),  # nrOfHits = 1
                                        AbilityOrEffect(this.Id), <options> )

    Le coup porte sur la CIBLE, qui vient de mourir : il n'entame donc RIEN, et son seul effet
    observable est la `LeftOverDamage` qu'il laisse (base nominale, cf.
    `operations/left_over_damage.py`) et que `HazeOfCorruption_DamageTransferEffect` reporte sur le
    relais. C'est l'implementation native du « + 1x Toxic Damage » de l'i2 : le jeu tape le cadavre
    pour que le coup DEBORDE, il ne l'adresse pas directement au relais.

    MESURE LIVE (`probe_209_haze_damage_transfer.py`, seed 777 et 88, PV cible 5000) : un evenement
    de degat `DamageProfileType 24`, `Passive_Ability_Type 1076`, `Amount 0` sur la cible, emis
    APRES les 3 coups d'arme et AVANT `Unit_IsDying` ; le relais recoit ensuite **1397** en profil
    24 -- la meme valeur sur les DEUX seeds, donc la base nominale et non un jet.

    Le gate `NOT TriggeringEffectIs(0x435)` (anti-chaine : un mort cause par un transfert 1077 ne
    re-declenche PAS le bonus) est lu sur le champ natif `TriggeringAbility` (`AbilityEntities+0x98`)
    via `_triggering_ability_or_effect` -- sur le vecteur MORT il vient de
    `state.trigger_ability_type`, que `_verify_deaths` alimente avec le `killTrigger` de la file
    (mirror de `KillUnitOptions+0x04`, #301 ; le canal `+0x60` y est VIDE cote natif).
    MESURE qui l'exigeait (`probe_220_haze_bonded_chain.py`, k = 2, seed 777, hp 1200) : le
    natif n'emet AUCUN coup bonus a la mort des relais, le port en emettait DEUX de plus."""
    event_id = _ON_PRE_UNIT_DEATH

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : le porteur est l'AUTEUR du coup fatal (slot Actor@0x158 = killer).
        if ev.killer_id is None or int(ev.killer_id) != int(self.owner_id):
            return False
        # `NOT IsDead(Owner@0x148)` : le porteur doit etre vivant.
        e = state.get_entity(self.owner_id)
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is not None and not uc.alive:
            return False
        # `IsDead(Target@0x178)` : la cible de l'evenement est bien celle qui meurt.
        if ev.dying_id is None:
            return False
        # `NOT TriggeringEffectIs(0x435)` -- slot `AbilityEntities+0x138` (cf. la docstring).
        return _triggering_ability_or_effect(state, ev) != HAZE_DAMAGE_TRANSFER

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.get_entity(ev.dying_id) is None:
            return None
        # `AttackDamage(Owner@0x148, Target@0x178, Get(extraDmg), Direct(Toxic), Get(nrOfHits), ...)`
        # = UNE feuille, sur une cible NOMMEE (`Target@0x178`) : aucun selecteur a evaluer. On appelle
        # donc directement l'Operation que la feuille appelle en dessous -- la cible vient de tomber,
        # et les selecteurs du port ne rendent que du VIVANT alors que le natif frappe bel et bien le
        # cadavre (`Amount 0` mesure), pour que le coup DEBORDE en `LeftOverDamage`.
        bmin, bmax, pierce, hits = ability_attack_params(
            state, self.owner_id, HAZE_OF_CORRUPTION_ABILITY, HAZE_BONUS_PROFILE,
            min_key=HAZE_EXTRA_DMG_KEY, max_key=HAZE_EXTRA_DMG_KEY, hits_key="nrOfHits",
            level_slot="passive")
        atk = AttackDamageOperation.execute_ability_attack(
            state, self.owner_id, ev.dying_id, bmin, bmax, pierce, hits,
            damage_profile=HAZE_BONUS_PROFILE, is_melee=True,
            ability_type=int(TriggeredAbilityType.HazeOfCorruption))
        return {"ability": HAZE_OF_CORRUPTION_ABILITY, "volet": "bonus_hit",
                "unit": self.owner_id, "target": ev.dying_id,
                "bounds": [bmin, bmax], "hits": hits,
                "total": (atk or {}).get("total")}


class HazeOfCorruptionDamageTransferTrigger(EffectTrigger):
    """`IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect` (0x435 = 1077) --
    le REPORT du degat gaspille sur le relais bonde. Cf. l'en-tete de module pour les deux
    fonctions natives (`$$CreateTargetTrigger` / `$$CreateTargetTriggerBehaviour`).

    `owner_id` = l'unite qui PORTE l'effet = le RELAIS ; `EffectSource` = la cible INITIALE ;
    `BondedEntityFromEffect` = le porteur du passif (Maladus).

    `bonded` (case-haze-bonded) est desormais l'entite REELLEMENT bondee, LUE sur l'instance d'effet
    (`BaseEffect.bonded`, mirror du champ `+0x10` du composant de bond ecrit par
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultBondEffectBuilder` et relu par
    `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`), et non plus INFEREE de « le tueur porte
    `HazeOfCorruption` ». Les trois usages natifs de `bonded` la prennent a la MEME source :
    `AreEqual(Actor@0x158, bonded)`, `IsAlive(bonded)` et l'ATTAQUANT du `Attack(bonded, Owner@0x148)`.

    REPLI (canal de SEED, pas approximation de port) : un effet 1077 SEEDE depuis `decisionView.effects`
    n'a pas de bonded -- le canal ne publie PAS le `BondedEntityId` (verifie : aucun champ `bonded` dans
    `frida/`). Dans ce SEUL cas, `_bonded_id` retombe sur l'ancienne inference. Un bond pose par le port
    (le chemin de production : le target-finder tire et bonde dans la MEME action que le coup fatal) a
    toujours son `bonded` renseigne.

    GATE `IsActive` (#231) : ce trigger vient de `$$CreateTargetTrigger`, donc du rail que
    `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` gate sur
    `EffectComponent.IsActive @+0x5c`. `matches` le lit sur l'instance (`BaseEffect.active`).

    NON PORTE : le repli `GetPersistentData` de `$$GetLeftOverDamages` (quand le contexte n'a pas
    de leftovers, le natif relit ceux de la cible INITIALE memorisee par le `SetPersistentData` du
    target-finder). Le port n'a pas de couche persistent-data d'ability ; ici la source de l'effet
    EST la cible initiale, donc la premiere lecture suffit sur les montages a un seul relais."""
    # `OnDeath(1, 1)` = `OnDeathEvent(**0** = UnitDeath, ...)` -- PAS `PreUnitDeath` (case-haze-bonded, cf. le
    # bloc `_ON_UNIT_DEATH` en tete de module). L'ordre natif de `KillUnitOperation$$Execute` est
    # `On(1)` -> `On(2)` -> `On(0)` -> `On(0x36 = UnitDefeated)` -> `On(0x35 = PostUnitKill)` : le coup BONUS (`On(1)`) precede
    # donc structurellement le REPORT (`On(0)`), au lieu de partager le meme vecteur.
    event_id = _ON_UNIT_DEATH
    effect_type = HAZE_DAMAGE_TRANSFER
    # `AbilityOrEffect(0x435)` que `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` ecrit
    # dans l'`AbilityEntities` AVANT le behaviour : tout ce que le report engendre (l'`Attack`, ses
    # `AttackDamage`, et la MORT du relais) porte cet id. C'est lui que lisent le
    # `TriggeringAbilityIs(AbilityOrEffect(0x435))` du trigger ci-dessous ET le
    # `NOT TriggeringEffectIs(0x435)` de `HazeCorruption_BonusHitAbility` (meme slot `+0x138`).
    TRIGGERED_ABILITY_ID = HAZE_DAMAGE_TRANSFER

    def _instance(self, state: State):
        """L'instance d'effet 1077 ACTIVE portee par `owner_id` (le relais)."""
        eff = getattr(state, "effects", None)
        if eff is None:
            return None
        for inst in (eff.by_unit.get(int(self.owner_id)) or []):
            if (not getattr(inst, "consumed", False)) and inst.effect_type == HAZE_DAMAGE_TRANSFER:
                return inst
        return None

    @staticmethod
    def _carries_haze(state: State, unit_id) -> bool:
        """Porteur du passif `HazeOfCorruption` -- ne sert PLUS qu'au repli SEED (cf. docstring)."""
        import gameconfig as GC
        e = state.get_entity(unit_id) if unit_id is not None else None
        if e is None:
            return False
        sc = e.get_component(StatsComponent)
        vid = getattr(getattr(sc, "ctx", None), "visual_id", None)
        if vid is None:
            uc = e.get_component(UnitComponent)
            vid = uc.visual_id if uc is not None else None
        return HAZE_OF_CORRUPTION_ABILITY in ((GC.unit(vid) or {}).get("passiveAbilities") or [])

    def _bonded_id(self, state: State, inst, ev: TriggerEvent):
        """`BondedEntityFromEffect(Effect@0x150)` = `ABondEffect$$BondedEntityId(effect)` = le champ
        `+0x10` du composant de bond -> `BaseEffect.bonded`. `None` = pas de bonded lisible (un effet
        1077 SEEDE ; cf. le REPLI de la docstring de classe)."""
        b = getattr(inst, "bonded", None)
        if b is not None:
            return int(b)
        if ev.killer_id is not None and self._carries_haze(state, ev.killer_id):
            return int(ev.killer_id)
        return None

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        inst = self._instance(state)
        if inst is None or ev.dying_id is None:
            return False
        # Gate `EffectComponent.IsActive @+0x5c` (#231) -- mirror du test que
        # `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` applique
        # AVANT d'evaluer le trigger de CIBLE de l'effet : dans sa boucle PAR CIBLE il RECHARGE
        # l'`EffectComponent` depuis l'entite-effet et n'appelle `ShouldTrigger` (slot 0x13) puis
        # `Execute` (slot 0x14) que `if (*(char *)(<component> + 0x5c) != '\0')`. Un effet INERTE
        # n'est donc meme pas EVALUE -- et une desactivation survenue en cours de drain stoppe les
        # cibles suivantes, ce que rend ici la re-evaluation par-item du pump collapse
        # (`triggers/dispatch/core.py::evaluate_trigger_operation`).
        # Ce gate est celui du rail TARGETS SEUL (`...HazeOfCorruption_DamageTransferEffect$$
        # CreateTargetTrigger`) : `EvaluateEffectTriggerEffectAbilities`, l'autre rail, n'accede
        # JAMAIS a `+0x5c` (case-229) -- l'y poser eteindrait les `ActivateEffect` qui RALLUMENT.
        if not inst.active:
            return False
        # `AreEqual(Target@0x178, EffectSource(Effect@0x150))` : c'est bien la cible INITIALE du bond
        # qui meurt.
        if int(getattr(inst, "source", -1) or -1) != int(ev.dying_id):
            return False
        bonded = self._bonded_id(state, inst, ev)
        if bonded is None:
            return False
        # `OnDeath & (TriggeringAbilityIs(0x435) | AreEqual(Actor@0x158, bonded))` -- EGALITE d'entite,
        # plus une inference sur le kit du tueur (case-haze-bonded).
        chained = _triggering_ability_or_effect(state, ev) == HAZE_DAMAGE_TRANSFER
        if not chained and (ev.killer_id is None or int(ev.killer_id) != bonded):
            return False
        # `IsAlive(bonded)` : le BONDE (pas le tueur) doit etre vivant pour que le report parte.
        b = state.get_entity(bonded)
        uc = b.get_component(UnitComponent) if b is not None else None
        return not (uc is not None and not uc.alive)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        inst = self._instance(state)
        if inst is None:
            return None
        # L'ATTAQUANT du `Attack(bonded, Owner@0x148, beh)` -- et de chaque `AttackDamage(bonded, ...)`
        # -- est le BONDE, lu sur l'instance (case-haze-bonded), PAS l'auteur du coup fatal.
        bonded = self._bonded_id(state, inst, ev)
        if bonded is None:
            return None
        dmgs = left_over_damages(state, ev.dying_id)
        # `beh = Nothing() + GetRemoveEffectBehaviour()` : le bond est consomme AVANT les coups.
        RemoveEffect(HAZE_DAMAGE_TRANSFER, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id),
            ExecutionContext(state=state, rng=state.rng))
        # `foreach d in dmgs : AttackDamage(bonded, Owner@0x148, Get(d.amount), Direct(d.type),
        #                                   One@0xc0, AbilityOrEffect(0x435))`
        # puis `Attack(bonded, Owner@0x148, beh)` -- l'attaquant est le BONDED, la cible le RELAIS.
        #
        # `On(PreAttack = 5)` -- **UNE SEULE FOIS, ICI**, et c'est LU (#925-r2, cable par #944).
        # `$$CreateTargetTriggerBehaviour` accumule les N feuilles par `op_Addition` dans **UN SEUL**
        # `IdunBattleLogic.Entities.DSLBehaviors$$Attack(bonded, Owner@0x148, beh)` -- donc UN SEUL
        # `IdunBattle.Entities.Behaviours.AttackBehaviour`, donc UN SEUL `StartAttack` (slot 58) ->
        # `StartAttackOperation$$Execute` -> `EvaluateAbilitiesImmediately(5)`. Les feuilles, elles,
        # sont des `DSLBehaviors$$AttackDamage` **NUES** (aucun `AttackBehaviour`) : elles portent
        # `is_outside_attack=False` et n'emettent RIEN, sans quoi le port en emettrait **N** la ou le
        # natif en emet **1**. Le port n'en emettait **aucune** avant #944 (le vecteur `amount`
        # n'exprimait pas le drapeau) : c'est cette emission-ci qui comble l'ecart.
        # ⚠ `ability_type=None`, et c'est LU AUX OCTETS, pas herite des feuilles : le 5e argument du
        # `$$Attack` englobant est un `AbilityOrEffect` **MIS A ZERO** juste avant l'appel
        # (`local_3b8 = 0 ; uStack_3b0 = 0 ; local_3a8 = 0`), alors que chaque feuille
        # `$$AttackDamage`, elle, recoit le vrai (`AbilityOrEffect$$op_Implicit` -> les 24 octets
        # recopies). Recopier `0x435` ici aurait donc INVENTE une valeur que le natif ne passe pas --
        # et elle n'est pas neutre : le slot 3 `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack`
        # commence par `if (!ability.HasValue) return false`, donc l'attaque englobante se declare
        # NON-ranged, ce qui est exactement ce que `None` produit cote port.
        if dmgs:
            from ..dispatch.attack import pre_attack_triggers
            pre_attack_triggers(state, int(bonded), int(self.owner_id), ranged=False,
                                ability_type=None)
        done = []
        for i, d in enumerate(dmgs):
            amount = int(d.get("amount") or 0)
            if amount < 0:
                continue
            entities = entities_from_state(state, bonded, self.owner_id, actor_id=bonded)
            ectx = ExecutionContext(state=state, rng=state.rng)
            # case-221 -- les N feuilles vivent sous UN SEUL `Attack(bonded, Owner@0x148, beh)`, donc
            # UNE SEULE serie de coups : `IsFirstHitInSeries()` (= `hitIndex == 0`) n'est vrai qu'a la
            # PREMIERE. Sans ce drapeau, chaque transfert etait « son propre coup 0 » et un transfert
            # de profil Toxic re-declenchait le `Maybe(25)` d'`OnToxicDamageAbility` -- un tirage EN
            # TROP, et une pose de `Contaminated` sur la tuile du RELAIS. MESURE : 2 seeds (13, 314)
            # dont le rang du flux qui suit les transferts passe sous 25 -> le live ne contamine
            # AUCUNE tuile, ni celle du relais ni une autre.
            # `amount_spread_pct` reste au DEFAUT 0 -- decision LUE, pas subie (#449-r2). Chaque
            # feuille native est un `IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage` dont le 8e
            # argument `Nullable<AttackDamageBehaviourOptions>` est passe VIDE (`local_328..local_308
            # = 0`), donc `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor`
            # (`GetValueOrDefault`) pose `+0x9e = 0` -> `$$ExecuteTarget` (options+0x2f) ->
            # `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (request+0x6a) ->
            # `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` branche PLATE
            # `MinMaxDamageFix64(d, d)`. Le montant transfere n'est PAS une base d'arme : c'est le
            # LeftOverDamage deja resolu, et l'etaler une seconde fois le fausserait.
            # MESURE live : forcer 20 ici fait diverger le relais de 38 points (hp 5000).
            AttackWithAttackDamage(Target(), HAZE_OF_CORRUPTION_ABILITY,
                                   d.get("profile") or HAZE_BONUS_PROFILE,
                                   is_melee=True, amount=Const(amount), hits=1,
                                   level_slot="passive",
                                   # #925-r2 : feuille `DSLBehaviors$$AttackDamage` **NUE** -- aucun
                                   # `AttackBehaviour` propre, donc AUCUN `StartAttack`. C'est
                                   # l'englobant `$$Attack` (emis une fois plus haut) qui ouvre
                                   # l'attaque ; sans ce `False`, le port emettrait N `On(5)` la ou
                                   # le natif en emet 1.
                                   is_outside_attack=False,
                                   is_first_hit=(i == 0)).execute(entities, ectx)
            done.append(amount)
        return {"ability": HAZE_OF_CORRUPTION_ABILITY, "volet": "damage_transfer",
                "unit": self.owner_id, "source": ev.dying_id, "bonded": bonded,
                "killer": ev.killer_id, "transferred": done}
