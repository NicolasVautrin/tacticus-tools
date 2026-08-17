"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Hailstrike_AttackAbility` (TriggeredAbilityType
0x5e3 = 1507) — le 2e maillon de la PHASE 2 de Hailstrike (case-117) : quand un ALLIE porteur du buff
1509 termine une attaque RANGED/OVERWATCH sur un ennemi, la MACHINE OF WAR (`darkaStormSpeeder`)
attaque la MEME cible.

REGISTRE (comment cette ability arrive sur la MoW) — `idun.Idun.Source.Shared.Battle.StaticBattleRules.
StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities` : dict statique peuple par
`...StaticBattleRules.ActiveAbility$$.cctor`, `ActiveAbilityType -> List<TriggeredAbilityType>`.
Entree LUE au decompile : **`0x4be (1214 Hailstrike) -> [0x5e3 (1507 Hailstrike_Attack)]`**. Donc toute
unite qui POSSEDE l'ability active 1214 porte, des l'init, le trigger 1507 -- INDEPENDAMMENT de tout
cast : c'est le gate `HasEffect(unit@0x158, 0x5e5)` du trigger qui le rend inerte tant que personne ne
porte le buff. Cote port : registre `ACTIVE_ABILITY_TRIGGERS` (dispatch.py), clé = le NOM gameconfig de
l'ability active (`units.activeAbilities`).

TRIGGER — `...Hailstrike_AttackAbility$$CreateTrigger` (MIRROR 1:1 du decompile) :

    On(9 = Attack, 1)
  & !AreEqual(unit@0x158, owner@0x148)                  # l'attaquant n'est PAS la MoW elle-meme
  & AreFriends(owner@0x148, unit@0x158)                 # ... c'est un ALLIE de la MoW
  & AreEnemies(owner@0x148, target@0x178)               # ... qui a vise un ENNEMI de la MoW
  & !IsDefeated(target@0x178)                           # la cible a survecu a l'attaque declenchante
  & HasEffect(unit@0x158, 0x5e5 = 1509, onlyActive=0, targetType=6)   # l'allie porte le buff Hailstrike
  & ( IsRangedAttack(df@0x130) | IsOverwatchAttack(df@0x138) )        # DISJONCTION, comme le percage

BEHAVIOUR — `...Hailstrike_AttackAbility$$CreateBehaviour(abilityState, triggerType)` (BODY GSHARED ;
`triggerType` = `IdunBattle.DSL.EventTriggerType`, cf. la signature du dump) :

    triggerType == 0x20 (= Custom)  :  If( !IsDefeated(target@0x178),
                                           AttackWithAbilityDamage( owner@0x148, target@0x178,
                                               MinMaxDamage(abilityState),
                                               Nullable(GetDamageProfileOrDefault(0x14 = Piercing)),
                                               GetNumberConstant(0x2f = nrOfHits),
                                               AbilityOrEffect(this.Id = 1507) ) )
    sinon                           :  TriggerAbilityDelayed( owner@0x148, this.Id, 3 )

Meme forme que `MasterOfTheTutelaries_SummonAbility` (#202-C) : le fire INITIAL (venu du vrai `On(9)`)
planifie un re-declenchement DIFFERE kind-3 de LA MEME ability, et c'est le REVEIL differe
(`triggerType == Custom`) qui execute l'attaque reelle. Le port COLLAPSE ce differe : l'attaque part
inline a la fin du vecteur `On(9)` -- meme point d'ordre observable (le vecteur est deja dispatche a
FinishAttack, donc apres resolution complete de l'attaque declenchante). L'ordre exact vis-a-vis
d'AUTRES triggers `On(9)` de la meme attaque = RESIDU (identique a #202-C).

PARAMETRES DE L'ATTAQUE, tous LUS (jamais devines) :
  * `MinMaxDamage(abilityState)` = `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage` =
    `RandomAmount(GetVariableForLevel(0xc = minDmg), GetVariableForLevel(0xd = maxDmg))` sur la CONFIG
    de l'ability (`this+0x20`), qui est celle de 1214 (`GetActiveAbilityUsedForConfig`) -> `minDmg`/
    `maxDmg` de la config `Hailstrike`, indexes par le niveau d'ability ACTIVE de la MoW, et
    rarity-scales (`variablesAffectedByRarityBonus` = [minDmg, maxDmg]).
  * profil = `GetDamageProfileOrDefault(0x14)` =
    `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetDamageProfileOrDefault` =
    `config.GetDamageProfile() ?? Piercing(0x14)`. La config 1214 DEFINIT `damageProfile = Projectile`
    -> le defaut `Piercing` n'est PAS retenu (piege : la constante 0x14 du decompile n'est pas le profil).
  * coups = `GetNumberConstant(0x2f)` = constante `nrOfHits` de la config 1214.
  * factory = `AttackWithAbilityDamage` -> famille ABILITY (`is_attack_damage_op=False`) : 1 tirage par
    coup, AUCUN crit, mods ATTAQUANT vides, arrondi `Round(AwayFromZero)` (cf. `execute_ability_attack`).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from .....entities.damage_profile_type import DamageProfileType
from .....entities.effect_type import EffectType
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....state import State
from ....components import OwnerComponent, StatsComponent, UnitComponent
from ..base import TriggeredAbility, TriggerEvent
from .....entities.effects.magnitude import ability_var
from ....abilities.base import profile_pierce, ability_pierce_effect_bonus
from ...damage import AttackDamageOperation

HAILSTRIKE_ABILITY = "Hailstrike"                            # ActiveAbilityType 0x4be = 1214 (config)
HAILSTRIKE_EFFECT = int(EffectType.Hailstrike)               # 0x5e5 = 1509 — le buff porte par l'ALLIE
HAILSTRIKE_ATTACK_TRIGGERED = int(TriggeredAbilityType.Hailstrike_Attack)   # 0x5e3 = 1507 (AbilityOrEffect)


#: `GetDamageProfileOrDefault(0x14)` — le DEFAUT natif si la config d'ability ne definit pas de profil.
#: `DamageProfileType(20) = Piercing`. La config 1214 en definit un (`Projectile`) -> ce defaut n'est
#: JAMAIS retenu pour Hailstrike ; il reste porte pour ne pas maquiller le decompile.
_DEFAULT_PROFILE = DamageProfileType.Piercing.name


def _damage_profile_or_default() -> str:
    """`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetDamageProfileOrDefault(defaultValue)` =
    `AbilityConfiguration.GetDamageProfile() ?? defaultValue`. Cote port, `GetDamageProfile()` = la
    constante `damageProfile` de la config d'ability (oracle = gameconfig, valeur BRUTE)."""
    import gameconfig as _GC
    v = ((_GC.ability(HAILSTRIKE_ABILITY) or {}).get("constants") or {}).get("damageProfile")
    return str(v) if v else _DEFAULT_PROFILE


def _team_of(state: State, uid: Optional[int]):
    e = state.get_entity(uid) if uid is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _is_defeated(state: State, uid: Optional[int]) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$IsDefeated(target)` — la cible est-elle morte ?
    Entite absente = consideree defaite (aucune attaque a lancer)."""
    e = state.get_entity(uid) if uid is not None else None
    if e is None:
        return True
    uc = e.get_component(UnitComponent)
    return uc is not None and not uc.alive


class HailstrikeAttackAbility(TriggeredAbility):
    """`Hailstrike_AttackAbility` (triggered 1507) — cf. l'en-tete de module pour l'arbre natif complet.
    `owner_id` = la MACHINE OF WAR (l'unite qui POSSEDE l'ability active 1214), instanciee par le
    registre `ACTIVE_ABILITY_TRIGGERS` (mirror `GetDerivedTriggeredAbilities`)."""
    event_id = int(EventTriggerType.Attack)        # On(9, 1) — fin de CHAQUE attaque (normale ET ability)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        att, tgt = ev.actor_id, ev.target_id
        if att is None or tgt is None:
            return False
        if att == self.owner_id:                             # !AreEqual(unit@0x158, owner@0x148)
            return False
        mine = _team_of(state, self.owner_id)
        if mine is None:
            return False
        if _team_of(state, att) != mine:                     # AreFriends(owner, unit)
            return False
        t_team = _team_of(state, tgt)
        if t_team is None or t_team == mine:                 # AreEnemies(owner, target)
            return False
        if _is_defeated(state, tgt):                         # !IsDefeated(target)
            return False
        if state.effects is None or not state.effects.has_effect(   # HasEffect(unit, 0x5e5, 0, 6)
                att, effect_type=HAILSTRIKE_EFFECT):
            return False
        # IsRangedAttack(df@0x130) | IsOverwatchAttack(df@0x138). `ev.ranged` est la nature du coup
        # threadee par le vecteur (voie normale : arme selectionnee par adjacence ; voie ability :
        # `_is_ranged_position`, mirror `DSLFactory.IsRangedAttack`). L'OVERWATCH n'a pas de champ
        # d'evenement dedie cote port -> il emprunte la voie NORMALE et sera vu comme `ranged` des que
        # le mover n'est pas adjacent ; le cas overwatch-au-contact est un RESIDU documente (case-doc).
        return bool(ev.ranged)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`CreateBehaviour(.., Custom)` = `If(!IsDefeated(target), AttackWithAbilityDamage(owner,
        target, MinMaxDamage, profil config, nrOfHits, AbilityOrEffect(1507)))`. Le `TriggerAbilityDelayed`
        de la branche `!= Custom` est COLLAPSE (cf. en-tete) -> on execute directement le reveil.

        Le `If(!IsDefeated)` est RE-EVALUE ici (et pas seulement dans `matches`) : cote natif les deux
        gates sont sur des passes distinctes (trigger, puis reveil differe) et la cible peut mourir
        entre-temps -- ex. un AUTRE trigger `On(9)` de la meme attaque l'acheve."""
        if state.rng is None:                                # l'attaque consomme le RNG (1 tirage/coup)
            return None
        tgt = ev.target_id
        if _is_defeated(state, tgt):                         # If(!IsDefeated(target@0x178))
            return None
        e = state.get_entity(self.owner_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        if ctx is None:
            return None
        lvl = ctx.active_ability_level                       # MinMaxDamage(abilityState) : ability ACTIVE
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        bmin = int(ability_var(HAILSTRIKE_ABILITY, "minDmg", lvl, multiplier_pct=mult) or 0)
        bmax = int(ability_var(HAILSTRIKE_ABILITY, "maxDmg", lvl, multiplier_pct=mult) or 0)
        hits = int(ability_var(HAILSTRIKE_ABILITY, "nrOfHits", is_constant=True) or 0)
        profile = _damage_profile_or_default()               # GetDamageProfileOrDefault(0x14)
        if not hits:
            return None                                      # config incomplete -> pas d'attaque inventee
        # Percage du coup de la MoW : profil de la config + ses propres stats ExtraPierce(+Ranged) + les
        # `EffectBonus` de SES effets actifs. La MoW ne porte PAS son propre buff 1509 (il va a l'ALLIE)
        # -> ce terme est nul ici sauf si un tiers l'a buffee ; on le passe quand meme (mirror du natif,
        # qui evalue TOUJOURS `PiercingBonusForAttack` sur l'attaquant du coup).
        pbonus = ability_pierce_effect_bonus(state, self.owner_id, tgt, HAILSTRIKE_ATTACK_TRIGGERED,
                                             is_ranged=True)
        pierce = profile_pierce(ctx, profile, ranged=True, effect_bonus=pbonus)
        res = AttackDamageOperation.execute_ability_attack(
            state, self.owner_id, tgt, bmin, bmax, pierce, hits,
            damage_profile=profile, is_melee=False,
            ability_type=HAILSTRIKE_ATTACK_TRIGGERED,
            is_attack_damage_op=False)                       # factory native = AttackWithAbilityDamage
        return {"ability": "Hailstrike_Attack", "owner": int(self.owner_id),
                "attacker": int(ev.actor_id), "target": int(tgt),
                "hits": hits, "profile": profile, "pierce": pierce, "result": res}
