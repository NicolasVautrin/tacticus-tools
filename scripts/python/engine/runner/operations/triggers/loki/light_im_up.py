"""`LightImUp` (passif de kit d'`orksWarboss` << Boss Gulgortz >>, `TriggeredAbilityType` 0x44f =
1103) -- face **COMBAT / EXECUTION**.

i2 (`Abilities/LightImUp_CurrentLevelDescription`) : « After performing a normal attack, Boss
Gulgortz performs a second attack against the same enemy, dealing {nrOfHits}x {minDmg}-{maxDmg}
Projectile Damage. If the target is defeated, leftover hits are allocated to any random enemy target
within {range} hexes. »

⚠ **CE MODULE PORTE L'EXECUTION, PAS LA DECISION.** La face DECISION (le playbook d'utilite
`IdunBattle.AI.Playbook.Loki.LightImUpPlaybook`) est portee ailleurs, par
`engine/playbook/light_im_up.py` (#419-r1-tr5, `docs/rl/case-419-r1-tr5-light-im-up-playbook.md`), et
son existence ne dit RIEN de celle-ci : la face COMBAT etait un **NO-OP SILENCIEUX** (aucune entree
dans `ABILITY_TRIGGERS`), donc le passif ne frappait jamais offline.

⚠ **LES DEUX FACES NE PORTENT PAS LA MEME GATE, ET C'EST NATIF.** Le playbook gate son utilite sur
`IsMeleeAttack(case)` (`IBattleQuery` slot 2, cf. la case-doc #419-r1-tr5) ; l'EXECUTION, elle, ne
porte AUCUNE gate de melee -- son seul gate de volet est `IsInAttackRange(Caster, Target,
UnitSelectionType.OnlyTargetable)`. Recopier la gate de la face soeur (la tentation exacte que le
voisin de forme inspire) rendrait le passif muet sur toute attaque normale a distance.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite
================================================================================================
Slots `DSLSelectors` utilises (carte LUE dans `IdunBattleLogic.Entities.DSLSelectors$$
InitializeShared`, cf. `runner/abilities/blacktemplars.py`) : `+0x30 Owner · +0x48 Caster ·
+0x50 CasterTile · +0x60 Target`.

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility$$CreateTrigger`

    On(0x26 = NormalAttack, ownerNeedsToBeAlive: 0) & get_OwnerIsActor

`IdunBattleLogic.Entities.DSLTriggers$$On(triggerType, ownerNeedsToBeAlive)` -- le 2e argument est
le litteral **0** ici (`On(pvVar1, 0x26, 0)`), la ou `Drachnyen` passe 1. Aucun autre conjoint :
ni profil, ni type d'arme, ni adjacence.

## `...LightImUpAbility$$CreateBehaviour(this, abilityState, triggerType)`

Termine par `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd(volet1, volet2)` -- une SEQUENCE
(`CombinedBehaviour`), donc `Seq` cote port :

    profil = BaseTriggeredAbility$$GetDamageProfile()            # constants.damageProfile = Projectile
    nbase  = BaseTriggeredAbility$$GetHits()                     # GetNumberConstant(0x2f) = nrOfHits = 3
    hitsN  = DSLFormulas$$AttackHitsWithModifiers(Caster@+0x48, Target@+0x60, Direct(nbase))
    dmg    = DSLFormulas$$Cache( BaseTriggeredAbility$$MinMaxDamage(abilityState) )
    rng    = AbilityConfiguration$$GetNumberConstant(0x16)       # constants.range = 3
    sec    = DSLSelectors$$Cache(
                 DSLSelectors$$PickRandomly(
                     DSLSelectors$$Damageable(
                         DSLSelectors$$Unobscured(Owner@+0x30,
                             DSLSelectors$$SurroundingEnemies(unit      = Caster@+0x48,
                                                              unitTile  = CasterTile@+0x50,
                                                              range     = rng,
                                                              unique    = 1,
                                                              selection = OnlyAliveAndTargetable))
                         op_Subtraction Target@+0x60),
                     amount = 1, allowDuplicates = 0,
                     maxDuplicatesAllowed = 0x7fffffff, ignoreForcedTargets = 0),
                 matchAbilityEntities = 1)
    main   = DSLSelectors$$Cache(Target@+0x60, matchAbilityEntities = 0)

    volet1 = DSLBehaviors$$If(
                 DSLTriggers$$IsInAttackRange(Caster@+0x48, Target@+0x60,
                                              UnitSelectionType.OnlyTargetable),
                 DSLBehaviors$$Attack(Caster@+0x48, main,
                     DSLBehaviors$$AttackDamage(caster = Owner@+0x30, target = Target@+0x60,
                                                amount = dmg, damageProfile = Direct(profil),
                                                hits   = hitsN,
                                                abilityOrEffect = AbilityOrEffect(this.Id),
                                                options = <octet +3 = 1, reste 0>),
                     options = null),
                 else = null)

    volet2 = DSLBehaviors$$If(
                 DSLTriggers$$IsDead(main),
                 DSLBehaviors$$Attack(Caster@+0x48, sec,
                     DSLBehaviors$$AttackDamage(caster = Owner@+0x30, target = Target@+0x60,
                                                amount = dmg, damageProfile = Direct(profil),
                                                hits   = DSLFormulas$$NumLeftOverHits(
                                                             main, AbilityOrEffect(this.Id)),
                                                abilityOrEffect = AbilityOrEffect(this.Id),
                                                options = <octet +3 = 1, reste 0>),
                     options = null),
                 else = null)

    return volet1 & volet2

### Les SEPT lectures qui ne se devinent pas

1. **Aucune gate de MELEE cote combat** (cf. l'avertissement en tete). Le seul gate de volet 1 est
   `IsInAttackRange` -- `IdunBattle.Entities.Triggers.IsInAttackRangeAbilityTrigger$$ShouldTrigger`
   = `BattleQuery.<slot 0x41>(unit, GetUnitPosition(unit), target, GetNormalAttackType(unit))`,
   donc « la cible est-elle a portee d'ARME du caster depuis sa position ». Le port a deja ce
   foyer : `triggers/base._in_attack_range`.
2. **L'`unitSelectionType` d'`IsInAttackRange` n'est JAMAIS LU.** Le ctor le range (`+0x30`) et
   `$$ShouldTrigger` ne lit que `+0x10 state · +0x18 query · +0x20 rangedUnit · +0x28 target`.
   `OnlyTargetable(2)` est donc INERTE -- non porte, et c'est une lecture, pas un oubli.
3. **L'octet +3 du `Nullable<AttackDamageBehaviourOptions>` est pose a 1 sur LES DEUX volets**, et
   il coupe la couche de modificateurs de coups (`AttackDamageOperation$$GetAttackHits` rend la
   base sans appeler le slot 0xb6). Sans lui les modificateurs s'appliqueraient DEUX FOIS : le
   nombre de coups est deja calcule par un NOEUD (`AttackHitsWithModifiers` / `NumLeftOverHits`).
   Chaine d'offsets complete : docstring de `AttackDamageOperation.execute_ability_attack`.
4. **`NumLeftOverHits(unit, abilityOrEffect)` n'a PAS de terme `extraHits`.**
   `IdunBattle.Entities.Formulas.NumLeftOverHitsFormula$$Calculate` = le `count` NU des entrees
   `LeftOverDamages` de l'unite dont le drapeau est vrai ET dont l'`AbilityOrEffect` egale le
   sien -- la ou `ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits` ajoute `+ extraHits`
   des que la liste est non vide. Le port partage donc le MEME foyer avec `extra = 0`.
5. **Le caster du `AttackDamage` est `Owner@+0x30`, pas `Caster@+0x48`** -- la factory standard
   `DSLBehaviors$$AttackWithAttackDamage` prend `Caster@+0x48` en dur. Pour un TRIGGERED,
   `Owner == Caster` (le porteur), donc observationnellement egal ; c'est ecrit ici parce que
   c'est ce que le decompile porte, pas parce que ca change quelque chose.
6. **`Attack(...)` OUVRE une attaque** (`AttackBehaviour$$.ctor`, comme les deux
   `AttackWith*Damage`) -> `isOutsideAttack = True` cote feuille : chaque volet pousse son propre
   `StartAttack`, donc son `On(PreAttack = 5)`, et l'index de coup repart de 0.
   ⚠ A ne pas confondre avec l'octet **+0** des options, qui vaut 0 -- lui commande le
   `GetCurrentAttackOrDefault` DU `AttackDamageBehaviour`, qui lit bien l'attaque que le
   `Attack(...)` englobant vient d'ouvrir. Les deux sont coherents, pas contradictoires.
7. **Le disque secondaire est ancre sur `CasterTile@+0x50`**, pas sur `Caster@+0x48`. Sur la face
   DECISION cette distinction TRANCHE (la tuile d'attaque candidate != la tuile reelle -- mesure
   #419-r1-tr5 section 6, deux valeurs qui divergent). Sur la face EXECUTION il n'y a pas de
   position candidate : `AbilityEntities.CasterPosition` est vide, donc `CasterTileSelector`
   retombe sur `GetTiles(Caster)` = la tuile REELLE. Le port ancre donc sur `Caster()` et le dit.

================================================================================================
RESIDUS NOMMES
================================================================================================
 * **HERITAGE du residu OUVERT `#505`** (pas un numero neuf : c'est le MEME foyer, pas un second
   defaut). `_left_over_hits`, partage avec `ChainLeftOverHitsAttackDamage`, porte la loi
   `max(0, H - k - 1)` qui SOUS-ESTIME le report d'exactement 1 quand le coup fatal ECRASE la cible
   (`DamagePrediction$$IsOverkill` est un SEUIL, pas un index). `LightImUp` en herite -- on ne le
   re-porte pas ici (une 2e loi serait une divergence garantie), on le NOMME.
 * **`#419-r1-tr5-r8`** -- les entrees `LeftOverDamages` sont derivees du RETOUR de l'attaque du
   volet 1 (`per_hit_health` / `hp_before`), pas d'une liste materialisee sur la cible. Le filtre
   natif `AbilityOrEffect == 1103` est donc porte par CONSTRUCTION (on ne lit que notre propre
   attaque) et non par un predicat : une entree laissee par une AUTRE source sur la meme cible
   dans le meme tour ne peut pas etre distinguee cote port. Aucun vecteur porte ne la produit.
"""
from __future__ import annotations

from typing import Optional

import gameconfig as GC

from .....dsl.base import AbilityTrigger, Const
import engine.dsl.base as _dsl_base   # FORME B (#923), et ABSOLUE
# `resolve_unit` etait re-importe DANS `should_trigger` alors que `engine.dsl.base` est deja
# charge par la ligne ci-dessus : ni cycle possible (l'arete existe), ni cout (le module est la).
# Le differe etait donc GRATUIT (`test_270r4r2r2_differes_offline::test_etage1_...`).
# ⚠ Le nom est lie via le MODULE et non importe directement : `migrate_485r1_barils_reexport.py
# morsure` ne classe pas ce couple HISSAGE_DESARMERAIT aujourd'hui, mais une liaison de module
# n'est jamais gelee -- un `monkeypatch.setattr("engine.dsl.base.resolve_unit", ...)` pose plus
# tard mordra encore. ABSOLUE plutot que `from .....dsl import base` : la forme relative
# declarerait une arete vers le PAQUET PARENT (meme mesure que `loki/attempted_possession.py`).
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, Seq
from .....entities.selectors.accessors import Owner, Target
from .....entities.selectors.geometry import PickRandomly
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import Damageable, Sub, SurroundingEnemies, Unobscured
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.behaviours.combat import AttackWithAttackDamage, ChainLeftOverHitsAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, _in_attack_range
from .....entities.triggers import IsDead

# Cle gameconfig de l'ability : le membre d'enum EST le nom de config. `GC.ability_name(1103)`
# rendrait `"Supercharge"` (l'index est celui d'`ActiveAbilityType` -- 1103 nomme TROIS artefacts :
# `TriggeredAbilityType.LightImUp`, `ActiveAbilityType.Supercharge`,
# `EffectType.KanOpener_ReduceArmor`). Cf. l'en-tete de `engine/playbook/light_im_up.py`.
LIGHT_IM_UP = TriggeredAbilityType.LightImUp.name                 # "LightImUp"
_ON_NORMAL_ATTACK = int(EventTriggerType.NormalAttack)            # On(0x26 = 38, 0)
# `AbilityConfiguration$$GetDamageProfile` = `constants.damageProfile`.
_CONST_PROFILE = "damageProfile"
# `LightImUpAbility$$CreateBehaviour` / `$$GetPossibleSecondaryTargets` : `GetNumberConstant(0x16)`.
_CONST_RANGE = "range"


def _profile_name() -> str:
    """`BaseTriggeredAbility$$GetDamageProfile()` -> `constants.damageProfile` (= "Projectile")."""
    return (((GC.ability(LIGHT_IM_UP) or {}).get("constants") or {}).get(_CONST_PROFILE) or "")


def _secondary_range() -> int:
    """`GetNumberConstant(config, 0x16)` = `constants.range` (= 3), rayon du disque secondaire."""
    return int(((GC.ability(LIGHT_IM_UP) or {}).get("constants") or {}).get(_CONST_RANGE) or 0)


class _IsInAttackRange(AbilityTrigger):
    """`IdunBattleLogic.Entities.DSLTriggers$$IsInAttackRange(rangedUnit, target, unitSelectionType)`
    -> `IsInAttackRangeAbilityTrigger$$ShouldTrigger` = `BattleQuery.<slot 0x41>(unit,
    GetUnitPosition(unit), target, GetNormalAttackType(unit))`.

    Le corps DELEGUE au foyer UNIQUE deja porte, `triggers/base._in_attack_range` (portee d'arme
    via `TargetingQuery$$GetRange`, clamp `ForcedInMelee` inclus) -- surtout pas un 2e port de la
    meme fonction native. `state` est capture a la construction : le `DslContext` d'un behaviour ne
    porte pas le `State` (meme precedent que `SortTargetsByDamagePrediction`, `blacktemplars.py`).

    Le 3e argument natif (`UnitSelectionType.OnlyTargetable`) n'est PAS porte : `$$ShouldTrigger`
    ne le lit jamais (cf. lecture 2 de l'en-tete)."""
    __slots__ = ("state", "ranged_unit", "target")

    def __init__(self, state: State, ranged_unit, target):
        self.state, self.ranged_unit, self.target = state, ranged_unit, target

    def should_trigger(self, ctx) -> bool:
        a = _dsl_base.resolve_unit(self.ranged_unit, ctx)
        t = _dsl_base.resolve_unit(self.target, ctx)
        if a is None or t is None or a.get("id") is None or t.get("id") is None:
            return False
        return _in_attack_range(self.state, int(a["id"]), int(t["id"]))


class _NumLeftOverHits:
    """`IdunBattleLogic.Entities.DSLFormulas$$NumLeftOverHits(unit, abilityOrEffect)` ->
    `IdunBattle.Entities.Formulas.NumLeftOverHitsFormula$$Calculate` : le nombre d'entrees
    `LeftOverDamages` de `unit` dont le drapeau est vrai ET dont l'`AbilityOrEffect` est le notre.
    **AUCUN terme `extraHits`** (contraste avec `GetLeftOverHits`, cf. lecture 4 de l'en-tete) ->
    `extra = 0`.

    Cote port les entrees ne sont pas materialisees sur la cible : elles se DERIVENT du retour de
    l'attaque qui les a produites (`per_hit_health` / `hp_before`), via le foyer PARTAGE
    `ChainLeftOverHitsAttackDamage._left_over_hits` -- qui porte le residu #505 (cf. en-tete).
    La source est l'`ExecutionContext` de CE cast : `ectx.emitted` porte le payload de l'attaque du
    volet 1, et lui seul (residu `#419-r1-tr5-r8`). Le noeud est evalue par
    `AttackDamageBehaviour$$ExecuteTarget` du volet 2, donc APRES le volet 1 -- l'ordre est celui du
    `Seq`, pas une commodite."""
    __slots__ = ("ectx",)

    def __init__(self, ectx: ExecutionContext):
        self.ectx = ectx

    def evaluate(self, entities) -> int:
        atk = None
        for name, payload in self.ectx.emitted:
            if name == "AttackWithAttackDamage" and payload.get("attack"):
                atk = payload["attack"]                    # dernier volet joue = le volet 1
        if atk is None:
            return 0
        return int(ChainLeftOverHitsAttackDamage._left_over_hits(atk, 0))


def light_im_up_secondary_selector(range_val: int):
    """`LightImUpAbility$$CreateBehaviour` (expression RECOPIEE inline, identique a
    `$$GetSecondaryTarget` -- meme corps, mais le natif ne l'appelle pas depuis `CreateBehaviour`) :

        DSLSelectors$$PickRandomly(
            DSLSelectors$$Damageable(
                DSLSelectors$$Unobscured(Owner@+0x30,
                    DSLSelectors$$SurroundingEnemies(Caster@+0x48, CasterTile@+0x50, range,
                                                     unique: 1, OnlyAliveAndTargetable))
                op_Subtraction Target@+0x60),
            amount = 1, allowDuplicates = 0, maxDuplicatesAllowed = 0x7fffffff,
            ignoreForcedTargets = 0)

    ANCRAGE (lecture 7 de l'en-tete) : le natif separe `unit = Caster` (reference d'EQUIPE) de
    `unitTile = CasterTile` (centre GEOMETRIQUE). Sur la face EXECUTION il n'y a pas de position
    candidate (`AbilityEntities.CasterPosition` vide -> `CasterTileSelector` retombe sur
    `GetTiles(Caster)`), donc les deux designent la MEME tuile et le port les collapse sur
    `Caster()`. Sur la face DECISION la distinction TRANCHE (mesure #419-r1-tr5 section 6) -- c'est
    pour cela qu'elle est ecrite ici plutot que tue.

    Le `Cache(..., matchAbilityEntities = 1)` natif qui enveloppe le `PickRandomly` n'est pas porte :
    le selecteur n'est evalue QU'UNE FOIS (par l'`Attack` du volet 2), donc le cache n'a aucun
    observable -- et le materialiser figerait un tirage RNG qui, lui, n'a lieu qu'une fois."""
    return PickRandomly(
        Damageable(
            Sub(Unobscured(SurroundingEnemies(Caster(), Const(int(range_val)),
                                              reference=Caster(),
                                              selection_type=int(
                                                  UnitSelectionType.OnlyAliveAndTargetable)),
                           from_ref=Owner()),
                Target())),
        amount=1, allow_duplicates=False, max_duplicates=0x7FFFFFFF,
        ignore_forced_targets=False)


def light_im_up_tree(state: State, ectx: ExecutionContext):
    """Arbre COMPLET de `LightImUpAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. l'en-tete pour le
    decompile terme a terme).

        Seq( If(IsInAttackRange(Caster, Target), Attack(Caster, Cache(Target), AttackDamage(...))),
             If(IsDead(Cache(Target)),           Attack(Caster, sec,           AttackDamage(...))) )

    `Cache(Target, matchAbilityEntities = 0)` n'est pas materialise : `Target()` lit le slot
    `+0x178` de l'`AbilityEntities`, que rien ne re-lie entre les deux volets -- la cible principale
    est donc deja FIGEE cote port, ce que le cache natif obtient explicitement.

    Les deux feuilles portent `skip_hits_modifiers=True` (octet +3 des options, lecture 3) :
      * volet 1 -- le natif applique les modificateurs par le NOEUD
        `AttackHitsWithModifiers(Caster, Target, Direct(nrOfHits))`. Le port les applique par le
        MEME foyer (`services/attack_hits_formula.attack_hits_with_modifiers`), mais depuis
        l'interieur de l'Operation : passer `hits = nrOfHits` avec le drapeau A **False** donnerait
        exactement le meme resultat (memes entrees, meme foyer). On le laisse donc a False ICI et
        on l'ecrit dans la docstring plutot que de dupliquer le noeud a l'exterieur -- sinon les
        modificateurs seraient comptes DEUX fois, ce que le drapeau natif interdit precisement.
      * volet 2 -- `NumLeftOverHits` rend un compte DEJA FINAL : le drapeau est a **True**, sinon
        un malus de coups de la cible SECONDAIRE (`Parry` / `LightCover` / `Camouflage`) rognerait
        une seconde fois un reste qui n'a jamais ete un nombre de coups d'arme.

    `is_melee=False` : `attackRangeType = "Ranged"` au gameconfig (LU, pas deduit du profil).
    `level_slot="passive"` : la config d'un PASSIF est resolue au niveau passif.
    `native_factory="attack"` (defaut) : la feuille native est bien `AttackDamageBehaviour`."""
    profile = _profile_name()
    main = AttackWithAttackDamage(Target(), LIGHT_IM_UP, profile, is_melee=False,
                                  level_slot="passive")
    sec = AttackWithAttackDamage(light_im_up_secondary_selector(_secondary_range()),
                                 LIGHT_IM_UP, profile, is_melee=False, level_slot="passive",
                                 multi=True, hits_override=_NumLeftOverHits(ectx),
                                 # octet +3 des options : le reste est deja final (cf. docstring)
                                 skip_hits_modifiers=True)
    # `IsDead(main)` -- `DSLTriggers$$IsDead(unit)` = `op_LogicalNot(IsAlive(unit))` (LU).
    return Seq(If(_IsInAttackRange(state, Caster(), Target()), main),
               If(IsDead(Target()), sec))


class LightImUpAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility` (triggered 1103, passif
    de kit d'`orksWarboss`) -- cf. l'en-tete du module.

        `On(0x26 = NormalAttack, 0) & get_OwnerIsActor`
        -> `If(IsInAttackRange(Caster, Target), Attack(3x Projectile sur la cible))
            & If(IsDead(Target),                Attack(coups restants sur 1 ennemi du disque r=3))`

    ⚠ **`fire_on_death` = VRAI (#10015) -- DEUX gates distincts, et le port n'en avait qu'un.**
    Le litteral `ownerNeedsToBeAlive: 0` de `On(0x26, 0)` (ci-dessus) vit dans le PREDICAT DSL ;
    `get_AllowForDeadOwner` est un gate SEPARE, en AMONT, applique par
    `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` avant toute evaluation de
    predicat. Les deux se lisent independamment, et ils sont ici tous les deux ouverts :
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility` surcharge
    `IdunBattle.Entities.Abilities.ITriggeredAbility` slot 8 et son corps rend VRAI (`b0 01 c3`,
    LU -- `metadata/allow_for_dead_owner.tsv`). Laisser `fire_on_death` au defaut FAUX referme donc
    en amont ce que le `0` du noeud `On` ouvre en aval : le Warboss tue par la riposte de sa propre
    attaque normale ne tirait plus.
    """
    event_id = _ON_NORMAL_ATTACK
    #: `ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` -> VRAI (cf. la docstring).
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` = `AreEqual(Owner@0x148, Actor@0x158)` -- le porteur EST l'attaquant.
        # C'est le SEUL conjoint du `CreateTrigger` : aucun gate de profil, d'arme ni d'adjacence
        # (cf. l'avertissement de l'en-tete : la gate de melee appartient au PLAYBOOK, pas ici).
        if self.owner_id != ev.actor_id:
            return False
        # `On(0x26, ownerNeedsToBeAlive: 0)` : le litteral est **0**, donc le natif n'exige PAS que
        # le porteur soit vivant. On ne pose donc aucune garde de vie sur le porteur -- l'ecrire
        # serait un conjoint invente.
        return ev.target_id is not None

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # `caster` = Owner@0x148 (triggered : Owner == Caster) ; `target` = la cible de l'attaque
        # normale qui vient de s'executer (`Target@0x178`, ce que `Cache(Target)` fige au natif).
        entities = entities_from_state(state, self.owner_id, ev.target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        light_im_up_tree(state, ectx).execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": LIGHT_IM_UP, "caster": int(self.owner_id),
                "target": ev.target_id,
                "attacks": [{"target": a.get("target"), "total": a.get("total")} for a in atks],
                "dsl": True}
