"""`MartialSuperiority` (passif de `templChampion` << Brother Jaeger >>, TriggeredAbilityType
0x444 = 1092) -- RIPOSTE : quand Jaeger est CIBLE d'une attaque de MELEE pendant le tour ADVERSE, il
frappe l'attaquant AVANT que l'attaque ne s'execute.

i2 : « If Brother Jaeger gets targeted with a melee attack from an adjacent enemy during the enemy's
turn, he deals 2x 1455-1601 Power Damage to the attacker before the enemy attack executes. »

================================================================================================
RE (decompile ghidra, build `gqfc5mff6c`) -- decompile = verite
================================================================================================
Slots `AbilityEntities` de `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` /
`$$.ctor` utilises ici : `0x90` ctx (non qualifie, cf. RESIDUS) · `0xa0` `IsTurnOf(Owner@0x148)` ·
`0x130` CurrentAbility (`CurrentAbilityIs` la lit) · `0x140` ability PARENTE ·
`0x148` Owner · `0x158` Actor · `0x178` Target.

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MartialSuperiorityAbility$$CreateTrigger`
(conjonction `AbilityTrigger.op_BitwiseAnd`, ordre de lecture du decompile)

    On(0x2a = PreUnitAbility, 1)
    & NOT ctx@0xa0                          # NOT IsTurnOf(Owner)  -> pendant le tour ADVERSE
    & IsDirectTargetAttack(@0x130)          # l'ability EN COURS est une attaque directe/normale
    & NOT IsDirectTargetAttack(@0x140)      # ... et n'est pas la FILLE d'une attaque directe
    & get_OwnerOrOwnerTileIsTarget          # AreEqual(Target@0x178, Owner) | AreEqual(Target, Tiles(Owner))
    & IsMeleeAttack                         # attaque de MELEE (predicat POSITIONNEL, cf. plus bas)
    & ctx@0x90                              # conjoint de contexte NON QUALIFIE (cf. RESIDUS)

`IdunBattleLogic.Entities.DSLTriggers$$IsDirectTargetAttack(df, sel)` =
`AbilityHasAttackTypeTrigger(sel, 0 = DirectTargetAttack) | IsNormalAttack(df, sel)` -- porte par
`abilities/attack_type.ability_is_direct_target_attack`. Les DEUX seuls call-sites natifs de ce
predicat (`list_xrefs`) sont ce `CreateTrigger` et
`IdunBattle.Entities.Effects.CounterAttackEffect$$GetDirectTargetAbilityTrigger`, qui batit le MEME
idiome `IsDirectTargetAttack(@0x130) & !IsDirectTargetAttack(@0x140)`.

`IdunBattleLogic.Entities.DSLTriggers$$IsMeleeAttack` (sans argument) construit un
`IsMeleeAttackAbilityTrigger`, dont la nature est **POSITIONNELLE** (caster adjacent a la cible),
cf. `triggers/base._is_ranged_position` -- c'est aussi ce qui porte le « from an ADJACENT enemy »
du texte i2.

## `...MartialSuperiorityAbility$$GetInitialTarget`

    return Actor@0x158          # l'ATTAQUANT (l'acteur de l'ability declenchante)

## `...MartialSuperiorityAbility$$CreateBehaviour`

    AttackWithAttackDamage( attaquant = Owner@0x148,
                            cibles    = Actor@0x158,
                            degat     = RandomAmount( GetVariableForLevel(0xc = minDmg, level),
                                                      GetVariableForLevel(0xd = maxDmg, level) ),
                            profil    = GetDamageProfile(cfg)              = "Power" (pierce 40),
                            nrOfHits  = GetNumberConstant(cfg, 0x2f)        = 2,
                            source    = AbilityOrEffect(this.Id = 1092) )

FAMILLE « attack » : le behaviour appelle `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`
(PAS `AttackWithAbilityDamage`) -> `native_factory="attack"` (defaut). `attackRangeType = Melee` ->
`is_melee=True`. La config d'un PASSIF est resolue au niveau passif -> `level_slot="passive"`.

## Le gate ACTEUR-MORT POST-`On(0x2a = PreUnitAbility)` -- ce qui rend « before the enemy attack executes » OBSERVABLE

`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`, sequence lue VERBATIM au decompile :

    FUN_1800280e0(0x4d, .., 0x2a);                     # On(PreUnitAbility)
    if (options@0x4a == 0 && IsUnit(caster) && IsDead(caster, state))  return 0;
    ... (bloc #120bis de RE-RESOLUTION DE CIBLE) ...
    ... execution de la behaviour ...

Le port avait le gate acteur-mort en TETE d'operation (#70) et le bloc #120bis, mais PAS cette
re-verification APRES l'evenement -- or c'est elle qui ANNULE l'attaque entrante quand la riposte
TUE l'attaquant. Elle est desormais portee sur les DEUX voies (`damage_ops.execute` pour l'attaque
normale, `AbilityHandler.visit_ActiveAbilityMessage` pour un cast), au MEME rang que le natif.

## Second artefact du passif : `MartialSuperiorityAddEffectAbility` (NON PORTE, sans observable)

`classes.tsv` : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MartialSuperiorityAddEffectAbility
: IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` -- pose
`IdunBattle.Entities.Effects.Loki.MartialSuperiority_VisualEffect : BaseEffect` sur le porteur.
Cette classe n'override QUE `CreateActiveCondition` (= `NOT IsTurnOf(owner@0xa0)`) : aucun
`CreateEffect*`, aucun stat-mod -> effet purement VISUEL (le halo « riposte armee » pendant le tour
adverse). Non porte : zero contribution moteur.

================================================================================================
RESIDUS EXPLICITES
================================================================================================
 * `NOT IsDirectTargetAttack(@0x140)` : `@0x140` est le 3e selecteur d'ability du factory (aux cotes
   de `@0x130` CurrentAbility et `@0x138` TriggeringAbility) ; `AbilityEntities` expose bien un
   `get_ParentAbilityType` (propage par `AttackBehaviour$$GetAttackOptions`), ce qui en fait
   l'ability PARENTE. Le port ne materialise PAS de chaine parent d'ability : il n'emet `On(0x2a = PreUnitAbility)`
   que depuis les DEUX portes d'operation top-level (`damage_ops.execute`,
   `AbilityHandler.visit_ActiveAbilityMessage`), jamais depuis une attaque FILLE (une riposte /
   un splash appellent directement `AttackDamageOperation`). Le conjoint est donc VRAI par
   construction sur tous les vecteurs portes -> non materialise, et documente ici.
 * `ctx@0x90` : noeud-trigger SINGLETON du factory (classe instanciee UNIQUEMENT dans
   `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`, et lu UNIQUEMENT par ce `CreateTrigger` dans tout le binaire).
   Il ne recoit que le service `factory@0x28` -- aucun owner/cible -> il ne peut porter qu'une
   condition GLOBALE. Non qualifie, non porte (MEME traitement que le conjoint `ctx@0x98` des
   `Triggered()` d'overwatch, case-127 §8.3 : « vrai dans l'execution reelle, la mesure live
   tranche »). La mesure live de ce cas confirme que la riposte part.
 * Le natif `AttackWithAttackDamage` recoit `AbilityOrEffect(this.Id)` = **1092 en
   TriggeredAbilityType**. Le canal `ability_type` du port est keye sur l'espace
   `ActiveAbilityType`/AbilityOrEffect des gates `IsNormalAttack`/`AbilityHasAttackType` -- y
   injecter 1092 collisionnerait avec `ActiveAbilityType 1092 = DarkTalonStrike`. Non threade
   (MEME choix que `MartialApotheosis`, qui recoit lui aussi son propre id).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from .....entities.selectors.accessors import Actor
from ....state import State
from ....components import OwnerComponent, UnitComponent
from ....abilities.attack_type import ability_is_direct_target_attack
from ..base import TriggeredAbility, TriggerEvent, _is_adjacent_units
from .....dsl.effects import ExecutionContext
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state

MARTIAL_SUPERIORITY = "MartialSuperiority"
_ON_PRE_UNIT_ABILITY = int(EventTriggerType.PreUnitAbility)     # On(0x2b = 43, 1)
_PROFILE = "Power"          # `GetDamageProfile(cfg)` -> constants.damageProfile = "Power"


def martial_superiority_tree():
    """UNE feuille `AttackWithAttackDamage` sur l'ATTAQUANT -- mirror de
    `MartialSuperiorityAbility$$CreateBehaviour` : le selecteur de CIBLES natif est litteralement le
    slot `Actor@0x158` du factory (== ce que rend `$$GetInitialTarget`), porte par le selecteur
    `Actor()` (`entities/selectors/accessors.py`, meme slot). `nrOfHits`(=2) coups du profil "Power"
    (pierce 40), bornes `MinMaxDamage(minDmg/maxDmg[level])` au `level_slot="passive"`,
    `native_factory="attack"` (defaut, la factory native est bien `AttackWithAttackDamage`).
    `multi=False` = collapse MONO-CIBLE (le slot `Actor` ne porte qu'UNE entite).
    Import paresseux (evite le cycle triggers <-> abilities.behaviours, == martial_apotheosis)."""
    return AttackWithAttackDamage(Actor(), MARTIAL_SUPERIORITY, _PROFILE,
                                  is_melee=True, level_slot="passive")


class MartialSuperiorityRiposteAbility(TriggeredAbility):
    """`MartialSuperiorityAbility` (triggered 0x444 = 1092, passif `templChampion`) -- cf. en-tete.

        `On(PreUnitAbility) & NOT IsTurnOf(Owner) & IsDirectTargetAttack(@0x130)
         & NOT IsDirectTargetAttack(@0x140) & OwnerOrOwnerTileIsTarget & IsMeleeAttack & ctx@0x90`
        -> `AttackWithAttackDamage(Owner -> Actor@0x158, 2 coups Power [minDmg,maxDmg])`
    """
    event_id = _ON_PRE_UNIT_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        # `get_OwnerOrOwnerTileIsTarget` = AreEqual(Target@0x178, Owner) | AreEqual(Target, Tiles(Owner)).
        # Le port n'a qu'UNE cible d'evenement (une entite) -> la 2e branche (cible = la TUILE du
        # porteur) est structurellement couverte par la 1re (aucun vecteur porte ne cible une tuile
        # d'unite occupee).
        if ev.target_id != self.owner_id:
            return False
        if ev.actor_id is None or ev.actor_id == self.owner_id:
            return False
        # `IsDirectTargetAttack(@0x130)` : l'ability EN COURS (attaque normale = kind 0x3f5, ou une
        # active de type DirectTargetAttack). Un soin / un buff adverse ne reveille PAS la riposte.
        if not ability_is_direct_target_attack(ev.ability_type):
            return False
        # `NOT ctx@0xa0` = `NOT IsTurnOf(Owner)` -> la riposte ne part QUE pendant le tour adverse.
        oc = owner.get_component(OwnerComponent)
        if oc is None or state.current_player_id is None:
            return False
        if int(oc.player) == int(state.current_player_id):
            return False
        # `IsMeleeAttack` -- predicat POSITIONNEL natif (`IsMeleeAttackAbilityTrigger` -> le caster
        # est ADJACENT a la cible), PAS la nature de l'arme (cf. `triggers/base._is_ranged_position`,
        # meme predicat en negatif). C'est aussi ce qui porte le « from an ADJACENT enemy » d'i2.
        #
        # ⚠ ON EXIGE UNE PREUVE POSITIVE D'ADJACENCE (`_is_adjacent_units`), on NE reutilise PAS
        # `_is_ranged_position` : son repli sans board rend False = « melee », ce qui est le sens
        # CONSERVATEUR pour son consommateur (splash Psyker : pas de re-trigger) mais le sens
        # PERMISSIF pour un trigger de riposte -- il ferait partir la riposte a distance des que le
        # board manque. Mesure : sans board, la riposte partait sur un attaquant a 9 hexes.
        if not _is_adjacent_units(state, ev.actor_id, self.owner_id):
            return False
        # L'attaquant doit etre une unite VIVANTE (cible de l'`AttackWithAttackDamage` qui suit) :
        # le pump peut l'avoir tue entre l'enfilement et le drain (`RunPhase` re-valide, cf.
        # `evaluate_trigger_operation`).
        att = state.get_entity(ev.actor_id)
        auc = att.get_component(UnitComponent) if att is not None else None
        return not (auc is not None and not auc.alive)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # `caster` = Owner@0x148 (triggered : Owner == Caster) ; `actor_id` = Actor@0x158, le slot
        # que le selecteur de cibles du behaviour natif lit litteralement.
        entities = entities_from_state(state, self.owner_id, actor_id=int(ev.actor_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        martial_superiority_tree().execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        atk = atks[0] if atks else None
        return {"ability": MARTIAL_SUPERIORITY, "caster": int(self.owner_id),
                "target": (atk.get("target") if atk else None),
                "attack": (atk.get("attack") if atk else None), "dsl": True}
