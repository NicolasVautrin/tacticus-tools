"""Le COUP DE PISTOLET de `HeavyBoltPistol` (1083) -- la face COMBAT (#419-r1-tr14-r4).

Face DECISION portee et confrontee par #419-r1-tr14 / -r1 (le playbook predit son propre montant) ;
celle-ci est l'EXECUTION : ce qui part REELLEMENT quand le porteur attaque.

## LE CANAL -- ce n'est PAS un trigger d'evenement, et c'est le point qui bloquait

`HeavyBoltPistolAbility` n'a **AUCUN** `$$CreateTrigger` : ni dans
`data/symbols/<build>/ghidra/functions.tsv`, ni dans le dump FRIDA `frida/methods.tsv` -- qui est
indexe PAR CLASSE et porte bien celui de `PsykerExtraAttackAbility`. Le passif n'entre donc dans
AUCUN registre d'`EventTriggerType`. Il est appele en dur, par l'attaque normale qu'il substitue :

    IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive
        1083 HeavyBoltPistol -> l'ACTIVE 1046 TemplarInitiateNormalAttack   (#419-r1-tr14-r5-r1)

    TemplarInitiateNormalAttackAbility$$ExecuteBehaviour
        b =   DSLBehaviors$$Group(<b__0>, DSLSelectors$$None(), GroupType.Ability_Attack = 0x20)
            & DSLBehaviors$$Group(<b__1>, DSLSelectors$$None(), GroupType.Ability_Attack = 0x20)
        return AActiveAbility$$ExecuteAtomic(b, entities,
                                             GroupType.TemplarInitiateNormalAttack_AtomicGroup = 0x52)

        <b__0> = $$ExecuteNormalAttack -> ALoki_NormalAttackAbility$$ExecuteBehaviour   # coups d'ARME
        <b__1> = $$ExecuteBonusAttack  -> AActiveAbility$$Execute(
                     DSLBehaviors$$TriggerAbility(entity = Caster@DSLSelectors+0x48,
                                                  abilityType = 0x43b = 1083,
                                                  actor = caster = Caster@+0x48,
                                                  target = Target@+0x60,
                                                  unitFeetTiles = null,
                                                  selectionType = 3, ignoreUnitHavingAbility = false))

L'ORDRE est donc ARME puis BONUS, dans le meme groupe atomique -- et c'est le rang auquel
`visit_AttackUnitMessage` insere ce module.

## L'ARBRE, LU

    HeavyBoltPistolAbility$$CreateBehaviour
        If( DSLTriggers$$IsMeleeAttack(<DSLTriggers+0x88>),          # surcharge a UN argument
            DSLBehaviors$$InformWeapon(GetDamageProfile(cfg), isMelee: true, useSpecial: null)
            op_BitwiseAnd
            DSLBehaviors$$AttackDamage(caster = Owner@DSLSelectors+0x30,
                                       target = Target@+0x60,
                                       amount  = DSLFormulas$$Direct(GetVariableForLevel(cfg, 0xb)),
                                       profile = DSLSelectors$$Direct(GetDamageProfile(cfg)),
                                       hits    = DSLFormulas$$Direct(GetNumberConstant(cfg, 0x2f)),
                                       abilityOrEffect = AbilityOrEffect(this),
                                       options = Nullable(<struct 0x20 a ZERO sauf l'octet +0 = 1>)),
            null )

* `0xb` = `AbilityVariableType.dmg`, la SEULE variable de la config -- pas de couple minDmg/maxDmg.
  Un `Direct(v)` est un montant a valeur UNIQUE : cote port, le mode BORNES avec `min_key == max_key`
  rend exactement `MinMaxDamageFix64(d, d)`, la meme entree de `AttackDamageOperation$$ExecuteHit`.
* `0x2f` = `AbilityConstantType.nrOfHits` (= 1 au gameconfig courant).
* le profil est celui de l'ABILITY (`Bolter`), **jamais l'arme du caster** : le corps ne consulte du
  caster ni arme, ni stat, ni trait -- seulement son identite, sa position et le niveau de son
  propre passif. C'est deja etabli et confronte par la face DECISION.
* `DSLBehaviors$$AttackDamage` construit un `AttackDamageBehaviour` **SEUL**
  (`targetSelectionType = 2 OnlyTargetable`), la ou `$$AttackWithAttackDamage` l'enveloppe d'un
  `AttackBehaviour` : c'est la meme feuille portee, en mono-cible (`multi=False`).
* `isMelee: true` d'`InformWeapon` est LU, pas deduit -- `DSLBehaviors$$InformWeapon(profile,
  isMelee, useSpecial)` inscrit la cle `0x92` = `TagKey.Attack_Weapon_IsMelee` depuis son 2e
  argument. Les deux autres cles sont `0x93` = `TagKey.Attack_Weapon_DamageProfile` (l'ORDINAL du
  `DamageProfileType`, ou `-1` = `None_` si le `Nullable` est vide -- ce n'est PAS un « weaponId »)
  et `0x94` = `TagKey.Attack_Weapon_Use_Special`, posee seulement si non nulle. Le natif DECLARE
  donc ce coup MELEE, et c'est ce qui fixe `is_melee=True` sur la feuille (l'axe `ExtraPierceMelee`
  vs `ExtraPierceRanged` de `profile_pierce`) ET le tag du flux.

## LA GATE -- geometrique, et MESUREE (elle n'etait pas devinable)

`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack(ability, caster, casterPosition, target)` :

    if (!ability.HasValue) return false;
    switch (GetAbilityAttackRangeType(ability)) {
      case 0 None:   return false;
      case 1 Melee:  return true;
      case 2 Ranged: return false;
      case 3 Normal: return !UnitExtensions.HasFlag(caster, 0x15 ForceRangedAttack)
                            && AreEntitiesAdjacent(casterPosition, target);
    }

et `$$GetAbilityAttackRangeType` lit l'`AttackRangeType` de la CONFIGURATION DE BATAILLE
(`BC.Abilities.*`), pas le gameconfig -- pour une `TriggeredAbilityType` il mappe les configs puis
passe par `$$SelectAbilityAttackRangeTypeFromMultiple`. Or `data/seed-bc.json` porte
`AttackRangeType: 0` pour `HeavyBoltPistol` : pris au pied de la lettre, la gate serait TOUJOURS
FAUSSE et ce bonus serait du code MORT. C'est la MESURE qui tranche, et elle dit l'inverse
(`probe_419r1tr14r4_heavy_bolt_pistol_bonus_attack.py`, deux hotes, bras apparie) :

| montage | hote (arme) | distance | TERME natif | coups natifs |
|---|---|---|---|---|
| `npc`   | `templNpc1Initiate:33` (`Chain`, melee) | contact | **+299 PV** | 2 -> **3** |
| `graft` | `tauMarksman` (`Piercing` 3, portee)    | contact | **+299 PV** | 1 -> **2** |
| `graft` | `tauMarksman`                           | 2 hex   | **+0 PV**   | 1 -> 1 |

Le zero a 2 hex n'est donc pas un regime degenere : le MEME montage rend `+299` au contact. La
branche effective est `Normal(3)` -- ni `Melee(1)` (qui rendrait vrai a 2 hex) ni `None(0)` (qui
rendrait faux au contact). Le montant, lui, est DECOMPOSE et non fitte : `(level 50, multiplier 180)`
mesures sur l'entite -> `ability_var(HeavyBoltPistol, dmg) = 1496`, puis percage `Bolter` 20 %
-> 299, identique sur les DEUX hotes (dont les armes different).

## DOCTRINE #149

`CreateBehaviour` = un VRAI arbre DSL (`Seq` = le `op_BitwiseAnd` natif, feuilles `InformWeapon` +
`AttackWithAttackDamage`) ; la frontiere reste le `.execute` des feuilles. Le `If` natif n'est PAS
enveloppe en noeud : sa condition est un slot d'`IBattleQuery` (runner-couple), evalue
imperativement par l'appelant -- exactement la meme frontiere que `primary_fold_tree` /
`is_melee_position` de `abilities/loki/additional_targets.py`.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ....dsl.effects import ExecutionContext
from ....entities.ability_constant_type import AbilityConstantType
from ....entities.ability_variable_type import AbilityVariableType
from ....entities.behaviours import op_add
from ....entities.selectors.accessors import Target
from ....entities.triggered_ability_type import TriggeredAbilityType
from ....entities.unit_flag import UnitFlag
from ....services.battle_query import is_melee_attack as _is_melee_attack
from ....services.custom_normal_attack import substitutes_normal_attack
from ..behaviours.combat import AttackWithAttackDamage, InformWeapon
from ..behaviours.context import entities_from_state
from ...components import PositionComponent, UnitFlagsComponent

if TYPE_CHECKING:
    from ...state import State

#: La cle gameconfig du passif -- c'est AUSSI la cle de la cascade
#: `UnitFactory$$AddNormalAttackAbility` (`CUSTOM_NORMAL_ATTACK_BY_PASSIVE`), donc le MEME substrat
#: d'ENTITE (`BC.Units[].PassiveAbilities`) que la face DECISION. Sans quoi les deux faces
#: decideraient de deux cascades differentes -- le vice ferme par #419-r1-tr14-r5.
PASSIVE = TriggeredAbilityType.HeavyBoltPistol.name              # "HeavyBoltPistol", 0x43b = 1083

#: `AbilityConfiguration$$GetVariableForLevel(cfg, 0xb)` -- la SEULE variable de la config.
_VAR_DAMAGE = AbilityVariableType.dmg.name
#: `AbilityConfiguration$$GetNumberConstant(cfg, 0x2f)`.
_CONST_HITS = AbilityConstantType.nrOfHits.name


def profile_name() -> str:
    """`AbilityConfiguration$$GetDamageProfile(cfg)` = `constants.damageProfile` de la config du
    PASSIF (`Bolter`), consomme par la feuille d'attaque ET par `InformWeapon`. Lu au gameconfig,
    jamais ecrit en dur : c'est le meme champ que la face DECISION."""
    return ((GC.ability(PASSIVE) or {}).get("constants") or {}).get("damageProfile") or ""


def bonus_attack_tree(profile: str):
    """L'arbre de `HeavyBoltPistolAbility$$CreateBehaviour`, SOUS son `If` -- MIRROR 1:1 :

        InformWeapon(GetDamageProfile(cfg), isMelee: true, useSpecial: null)
      op_BitwiseAnd
        AttackDamage(Owner@0x30, Target@0x60, Direct(GetVariableForLevel(0xb)),
                     Direct(GetDamageProfile(cfg)), Direct(GetNumberConstant(0x2f)),
                     AbilityOrEffect(this), options)

    `Seq` (= `op_add`) est la MEME classe native `CombinedBehaviour` que l'`op_BitwiseAnd` du
    decompile (cf. `entities/behaviours.py::Seq`) : sequence gauche->droite. `InformWeapon` est
    COMBAT-INERTE (pose de metadata d'arme, aucun tirage, aucune mutation de PV/stat), donc l'ordre
    ne deplace pas la consommation de `state.rng` -- il est porte pour MIRRORER la structure, comme
    partout ailleurs (precedent : `FlailSwing`).

    `Target()` porte `Target@0x60` : `TriggerAbility` reecrit l'`AbilityEntities` avec `target =
    Target@+0x60` de l'attaque normale, c'est-a-dire la cible du coup -- donc la cible que
    l'appelant vient reellement de frapper, pas celle du message.

    Le CASTER de la feuille est `Owner@0x30`, et sur cette voie il vaut le caster : `TriggerAbility`
    ecrit `actor = caster = Caster@+0x48`, et pour toute ability ACTIVE
    `ActiveAbilityOperation$$GetAbilityEntities` ecrit l'entite caster dans les TROIS slots
    `+0x00 Actor`, `+0x08 Caster` et `+0x18 Owner` (lecture etablie par #478-r4). Le port passe donc
    l'`AbilityEntities` monte par `entities_from_state(state, caster, target)`.

    MODE BORNES avec `min_key == max_key == dmg` : le natif passe un `Direct(v)`, montant a valeur
    UNIQUE ; `ability_attack_params` lit alors `ability_var(HeavyBoltPistol, dmg, <niveau du
    PASSIF>)` des deux cotes et `execute_ability_attack(bmin == bmax)` entre dans
    `AttackDamageOperation$$ExecuteHit` par `MinMaxDamageFix64(d, d)` -- la meme branche PLATE que le
    mode `amount` a variance nulle, mais SANS avoir a re-deriver le niveau hors du foyer.
    `level_slot="passive"` parce que `UnitFactory$$AddNormalAttackAbility` monte l'attaque normale
    substituee avec le `triggeredAbilityState` (`if (fromPassive.HasValue) { state =
    triggeredAbilityState; }`).

    `hits_key` = `nrOfHits` (`GetNumberConstant(0x2f)`), lu par le foyer sur la MEME config.

    `ability_type` N'EST PAS threade : l'`AbilityOrEffect(this)` natif porte une
    `TriggeredAbilityType`, pas une `ActiveAbilityType` -- et c'est OBSERVABLE, les evenements du
    coup bonus rendent `Active_Ability_Type = None` la ou les coups d'arme portent `1046`. Meme
    choix, pour la meme raison, que `triggers/loki/hateful_assault.py`.

    `force_overkill=False` / `force_crit=False` / mode bornes : les octets +4, +5 et +6 du
    `Nullable<AttackDamageBehaviourOptions>` sont a ZERO au call-site (la struct 0x20 est memset,
    seul l'octet **+0** est pose a 1).

    L'octet **+0 est `isOutsideAttack`** (#419-r1-tr14-r4-r1, RESOLU) -- le NOM est LU dans les
    metadonnees IL2CPP, pas deduit : `IdunBattle.Operations.ADamageOperation$$GetCurrentAttackOrDefault`
    declare `isOutsideAttack:System.Boolean`, et son corps route sur DEUX slots d'`IBattleQuery` :
    `false` -> slot 200 `GetCurrentAttackOrDefault` (l'`OngoingAttack` EN COURS si un contexte
    d'attaque existe, sinon une neuve), `true` -> slot 201 `GetDefaultAttack`, dont le corps est
    `new OngoingAttack()` INCONDITIONNEL. Le chemin : le ctor du behaviour recopie les 0x20 octets a
    `AttackDamageBehaviour+0x98`, `$$ExecuteTarget` les re-serialise dans
    `IdunBattle.Operations.AttackDamageOptions` (l'octet +0 y atterrit en **+0x2e**), et
    `AttackDamageOperation$$Execute` le passe en 1er argument de `GetCurrentAttackOrDefault`.

    CE QUE LE PORT EN FAIT : rien, et c'est le comportement JUSTE **ici** -- ce call-site est l'un
    des TROIS (sur 18) qui posent `1`. La feuille est montee par
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`, qui finit par
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor` et pousse donc un `OngoingAttack` NEUF
    par cible : c'est exactement la semantique `isOutsideAttack = true`. Poser le drapeau serait un
    no-op.

    ⚠ Ne pas generaliser cette phrase : la version d'avant #419-r3 disait << le port ne modelise
    AUCUNE `OngoingAttack` partagee >>, et c'etait FAUX des deux cotes. Cote natif, **15 des 18**
    call-sites de `IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage` posent `false` (balayage
    exhaustif : `docs/rl/case-419-r3-is-outside-attack-inexprimable.md`) ; cote port, trois champs de
    l'`OngoingAttack` sont threades depuis longtemps (`hit_index0` +0x30, `crit_allowed0` +0x40,
    `failed_block0` +0x48). Ce qui manquait etait une feuille d'attaque NUE -- un
    `AttackDamageBehaviour` SANS `AttackBehaviour` --, desormais exprimable par le champ
    `attack_state0` d'`AttackWithAttackDamage`. Le regime ou l'ecart MORD est le FOLD primaire de
    `Boltstorm`/`RighteousRepugnance` (`abilities/loki/additional_targets.py`), pas celui-ci."""
    return op_add(
        InformWeapon(profile, is_melee=True),   # `InformWeapon(profile, isMelee: 1, useSpecial: 0)`
        AttackWithAttackDamage(Target(), PASSIVE, profile,
                               is_melee=True,                    # `InformWeapon(..., isMelee: true)`
                               min_key=_VAR_DAMAGE, max_key=_VAR_DAMAGE,
                               hits_key=_CONST_HITS,
                               level_slot="passive",
                               multi=False))


def _pos_of(state: "State", uid: Optional[int]):
    e = state.get_entity(int(uid)) if uid is not None else None
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def is_melee_attack(state: "State", caster_id: int, target_id: Optional[int]) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` (slot 2 d'`IBattleQuery`) -- la gate du
    `If`, evaluee pour l'ability `HeavyBoltPistol`.

    Le SWITCH n'est PAS re-ecrit ici : il est DELEGUE au foyer
    `engine.services.battle_query.is_melee_attack`, qui le porte deja pour la face DECISION (un
    service natif appele par N chemins = UNE fonction). Le foyer prend son substrat geometrique en
    `elev_by_pos` / `neigh_by_pos` -- que le runner obtient de son `Board` par
    `walk_maps_by_pos()`, exactement comme le fait `operations/triggers/loki/empyric_ambush.py`
    (l'autre consommateur RUNNER de ce meme slot 2).

    `attackRangeType` de `HeavyBoltPistol` est ABSENT du gameconfig -> le foyer prend la branche
    `Normal(3)` (`!HasFlag(caster, ForceRangedAttack) && AreEntitiesAdjacent(casterPosition,
    target)`), et c'est ce que la MESURE confirme : contact `+299`, 2 hex `+0`, sur le MEME montage.

    `ForceRangedAttack` (`UnitFlag` 21) est LU sur le `UnitFlagsComponent` quand il existe. Le
    capteur `combatSnapshot.unitFlags` ne publie pas ce drapeau (residu `#419-r1-tr5-r1`, deja nomme
    par le foyer) : composant absent -> `False`, degradation PERMISSIVE-EN-PLUS et NOMMEE. On ne
    devine pas un drapeau qu'on ne mesure pas.

    Positions manquantes -> `False` : le natif deref sans garde, on ne mirroir pas une levee, et
    l'absence de position ne peut pas valoir « au contact »."""
    if target_id is None:
        return False
    cpos, tpos = _pos_of(state, caster_id), _pos_of(state, target_id)
    if cpos is None or tpos is None:
        return False
    board = state.board
    neigh = elev = None
    if board is not None:
        neigh, _walk, elev = board.walk_maps_by_pos()
    e = state.get_entity(int(caster_id))
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    forced = bool(fl is not None and fl.has(UnitFlag.ForceRangedAttack))   # HasFlag(caster, 0x15)
    return bool(_is_melee_attack(PASSIVE, cpos, tpos, elev_by_pos=elev,
                                 force_ranged_attack=forced, neigh_by_pos=neigh))


def has_bonus_attack(passive_abilities=None, active_abilities=None, visual_id=None, traits=None,
                     config_active_abilities=None) -> bool:
    """« L'attaque normale de CETTE entite est-elle celle que substitue `HeavyBoltPistol` ? »

    Delegue au FOYER de la cascade `UnitFactory$$AddNormalAttackAbility`
    (`services.custom_normal_attack.substitutes_normal_attack`), et surtout pas a un
    `1083 in passives` : une unite qui porte `HeavyBoltPistol` DERRIERE un autre passif substituant
    recoit l'attaque normale de l'AUTRE, donc n'execute PAS `TemplarInitiateNormalAttackAbility` et
    ne tire donc PAS le coup de pistolet. Meme raison, meme foyer que `additional_targets.cleave_for`."""
    return substitutes_normal_attack(PASSIVE, passive_abilities=passive_abilities,
                                     visual_id=visual_id, active_abilities=active_abilities,
                                     traits=traits,
                                     config_active_abilities=config_active_abilities)


def execute_bonus_attack(state: "State", caster_id: int,
                         target_id: Optional[int]) -> "Optional[dict]":
    """`TemplarInitiateNormalAttackAbility$$ExecuteBonusAttack` -> `TriggerAbility(1083)` ->
    `HeavyBoltPistolAbility$$CreateBehaviour`.

    Rend `{"target", "attack"}` quand le coup part, `None` quand la gate le coupe. L'appelant joue
    ceci APRES les coups d'arme (l'ordre natif des deux `Group` du `ExecuteAtomic(0x52)`) et AVANT
    `ExecuteTriggerAbilities` (`On(0x26)`).

    ⚠ L'ORDRE compte au-dela de l'affichage : chaque coup consomme `state.rng`. Le jouer AVANT les
    coups d'arme donnerait les BONS montants sur les MAUVAIS coups."""
    if target_id is None:
        return None
    if not is_melee_attack(state, caster_id, target_id):
        return None                                       # le `If(..., null)` natif
    ectx = ExecutionContext(state=state, rng=state.rng)
    entities = entities_from_state(state, int(caster_id), int(target_id))
    bonus_attack_tree(profile_name()).execute(entities, ectx)
    hit = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
    if hit is None:
        return None
    return {"target": hit.get("target"), "attack": hit.get("attack")}


__all__ = ["PASSIVE", "bonus_attack_tree", "execute_bonus_attack", "has_bonus_attack",
           "is_melee_attack", "profile_name"]
