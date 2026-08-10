"""PHASE 2 de `SeekerMissileFrequencyLock` -- la TRIGGERED `1127`, declenchee par le `Triggered()`
d'`IdunBattle.Entities.Effects.APendingAttackEffect` (`triggers/pending_attack.py`).

POURQUOI CE MODULE EST ICI, ET PAS DANS `abilities/tau.py` (#503-r3). Le noeud `TriggerAbility` de
`pending_attack_tree` fait son lookup dans `TRIGGERED_ABILITY_BEHAVIOURS`, que chaque module de
phase 2 alimente A SON IMPORT. Mesure du 2026-08-10, process FRAIS, n'important que la chaine
trigger (`dispatch/registry.py`) : `1134 FullThrottle` present (import pour effet de bord),
`1127` et `1237` ABSENTS -- registre a UNE entree. Le `Triggered()` rendait alors `dispatched:
False` **en retirant l'effet quand meme** (le `RemoveEffect` du meme arbre) : un marqueur consomme
sans que rien ne frappe, le regime que `pending_attack.py` Sec.2 declare PIRE que le statu quo.

LA REPARATION EST UN DEPLACEMENT, PAS UN IMPORT. Les deux aretes candidates n'etaient pas de la
meme classe (protocole du CLAUDE.md -- charger la cible SEULE dans un process frais) :

    `registry -> abilities.worldeaters` : worldeaters seul NE tire PAS registry  -> GRATUITE
    `registry -> abilities.tau`         : tau seul TIRE registry                 -> PORTEUSE
      chaine mesuree : tau -> attack_query -> revive_effect -> dispatch.ability
                           -> dispatch.core -> dispatch.registry

Hisser l'une et differer l'autre aurait inscrit une asymetrie que rien dans le natif ne justifie.
Le point (1) de la doctrine -- DEPLACER le code vers un module que la cascade ne re-entre pas --
supprime l'arete au lieu de la fermer : une ability TRIGGERED vit sous `operations/triggers/`, ou
`loki/full_throttle.py` (1134) portait deja exactement ce patron. `abilities/tau.py` garde son
ACTIVE `1069` (phase 1), qui pose l'effet de bond.

CE MODULE NE REMONTE VERS AUCUN MODULE D'ABILITIES CONCRETES : ses dependances
(`abilities/behaviours/*`, `entities/*`, `runner/components`) sont toutes neutres, mesure.

================================================================================================
`...Triggered.Loki.SeekerMissileFrequencyLock_AttackAbility$$CreateBehaviour(abilityState,
triggerType)` -- MIRROR 1:1 du decompile
================================================================================================

  hits      = AbilityConfiguration.GetNumberConstant( config@+0x20, 0x2f = nrOfHits )
  <BaseTriggeredAbility.MinMaxDamage(this, abilityState)>        # appelee, RESULTAT NON UTILISE
  effectSel = DSLSelectors.EffectFromOwner( Target@DSLSelectors+0x60, 0x463 = 1123 )
  stateSel  = DSLSelectors.AbilityStateFromEffect( effectSel )
  amount    = DSLFormulas.RandomAmount( ConfigVar(0xc = minDmg, stateSel, config@+0x20),
                                        ConfigVar(0xd = maxDmg, stateSel, config@+0x20) )
  profile   = BaseTriggeredAbility.GetDamageProfileOrDefault( this, 0x13 )
  attack    = DSLBehaviors.AttackWithAbilityDamage( caster = Caster@+0x48, target = Target@+0x60,
                                                    amount, Nullable(profile), hits,
                                                    AbilityOrEffect(this), selectionType = 2 )
  remove    = DSLBehaviors.RemoveEffect( Caster@+0x48, (int?)0x470 = 1136, null )
  return      AbilityBehaviour.op_BitwiseAnd( remove, attack )

TROIS POINTS DE FIDELITE, tous LUS :

1. `MinMaxDamage` EST APPELEE ET SON RESULTAT N'EST PAS CONSOMME (aucun registre ne le porte au
   site d'appel). Elle construirait `RandomAmount(GetVariableForLevel(0xc),
   GetVariableForLevel(0xd))` sur l'`abilityState` de l'ability DECLENCHEE ; le montant reellement
   passe a `AttackWithAbilityDamage` est l'autre, bati sur l'etat FIGE dans l'effet 1123. Elle ne
   consomme AUCUN tirage (les deux constructeurs rendent un NOEUD, le tirage a lieu au
   `Calculate`), donc l'ignorer est bit-exact. Ne pas la porter est le mirror ; la porter tirerait
   deux fois.

2. `GetDamageProfileOrDefault(0x13)` = `config.GetDamageProfile() ?? 0x13` (corps LU :
   `Nullable<DamageProfileType>.GetValueOrDefault(defaultValue)`). Le kit
   `SeekerMissileFrequencyLock` porte `damageProfile = HeavyRound`, donc le defaut `0x13` n'est
   JAMAIS atteint -- l'ecrire en dur serait un fit. Le port lit le profil du kit et ne modelise pas
   le defaut (residu #513-r2).

3. LE KIT EST PARTAGE PAR LES DEUX PHASES. `SeekerMissileFrequencyLock_Attack` n'a AUCUNE entree
   gameconfig propre (grep du gameconfig : une seule cle `SeekerMissileFrequencyLock`), et pourtant
   `this@+0x20` est non nul au runtime -- c'est la MEME `AbilityConfiguration` que l'active. Le
   site natif de cette attribution n'est pas RE'd (residu #513-r3) ; ce que la mesure etablit,
   c'est que `nrOfHits`, `damageProfile`, `minDmg` et `maxDmg` du kit sont consommes ICI, pas au
   cast.

ORDRE DU `op_BitwiseAnd` : le decompile EVALUE l'attaque d'abord et le retrait ensuite, mais passe
le retrait en PREMIER argument. Le port place l'attaque d'abord -- l'ordre est SANS CONSEQUENCE
MESURABLE ici (1136 est un `BaseEffect` inerte : aucune stat-mod, aucun tirage), et c'est ce que
`probe_513_seeker_phase2.py` verifie en jouant les deux ordres. Residu #513-r4.

NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : `BaseTriggeredAbility`, hors `ABILITY_CLASSES`.
ASCII only.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ....abilities.behaviours.combat import AttackWithAbilityDamage
from ....abilities.behaviours.effects import RemoveEffect
from ....abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
from ....components import StatsComponent
from .....dsl.base import Const
from .....entities.behaviours import op_and
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import RandomAmount
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....entities.triggered_ability_type import TriggeredAbilityType

if TYPE_CHECKING:                                  # pragma: no cover
    from ....state import State

#: Les identifiants du kit, DERIVES des enums (jamais un litteral). Ils vivent ICI et non dans
#: `abilities/tau.py` parce que le sens de l'arete est CONTRAINT : ce module doit etre chargeable
#: SEUL par `dispatch/registry.py`, alors que l'arete retour (`tau -> registry`) est PORTEUSE.
#: La phase 1 les importe donc d'ici -- UNE seule definition, pas deux derivations a garder en
#: phase.
SEEKER_MISSILE_FREQUENCY_LOCK_ID = "SeekerMissileFrequencyLock"
SEEKER_LOCK_TARGET = int(EffectType.SeekerMissileFrequencyLock_Target)   # 0x463 = 1123
SEEKER_LOCK_AIMING = int(EffectType.SeekerMissileFrequencyLock_Aiming)   # 0x470 = 1136
SEEKER_MISSILE_ATTACK = int(TriggeredAbilityType.SeekerMissileFrequencyLock_Attack)   # 0x467 = 1127


def seeker_missile_frequency_lock_attack_tree(state: "State", level: Optional[int],
                                              multiplier_pct: int):
    """Arbre de `...Triggered.Loki.SeekerMissileFrequencyLock_AttackAbility$$CreateBehaviour`.

    `level`/`multiplier_pct` = l'`AbilityState` que le natif va chercher par
    `AbilityStateFromEffect(EffectFromOwner(Target, 1123))`, c'est-a-dire l'etat FIGE dans l'effet au
    moment du cast -- resolu par l'appelant (`_seeker_missile_attack_behaviour`) sur l'INSTANCE
    d'effet, jamais sur l'etat courant du caster.

    `is_melee=None` -- ET C'EST LU, PAS CHOISI. Les QUATRE surcharges de
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` prennent
    `(caster, target, amount, damageProfile, hits, abilityOrEffect, [options,] selectionType)` :
    **aucune ne porte de bit melee/ranged**, et la chaine de delegation ne fabrique qu'un couple
    `(damageProfile, hits)`. Le noeud ne transporte donc AUCUNE nature de coup, ce que le port note
    deja pour le DoT de tuile -- `None` = `IsMeleeAttack` ET `IsRangedAttack` tous deux FAUX.
    ⚠ LE DISCRIMINANT EST DANS LE MONTAGE MEME, et il vaut exactement 15 % : la cible porte
    `1122 Markerlight` (pose par le MEME cast), dont le bonus `MarkerlightDmgBonusPct` est gate
    `IsRangedAttack`. Ecrire `is_melee=False` -- ce que le kit `attackRangeType = "Ranged"` invite a
    faire -- l'ARME cote defenseur : mesure, `6767` de degat avant block la ou le natif en fait
    `5884`, soit `x1.15` tout rond, et `4307` contre `3424` en PV. Le kit declare la portee de
    l'ABILITY (elle sert au ciblage) ; il ne declare pas la nature du COUP sur ce vecteur.
    `native_operation="ability"` : la factory native est `AttackWithAbilityDamage`, donc
    `IdunBattle.Operations.AbilityDamageOperation` (pas de crit, pas de resolve d'attaque)."""
    # DIFFERE et GRATUIT : `gameconfig` n'est pas un module `engine.*`, il n'entre dans aucun cycle
    # du paquet, et le hisser ferait payer le chargement du gameconfig a tout importeur -- donc a
    # `dispatch/registry.py`, qui importe ce module pour effet de bord.
    import gameconfig as GC
    consts = (GC.ability(SEEKER_MISSILE_FREQUENCY_LOCK_ID) or {}).get("constants") or {}
    hits = int(consts.get("nrOfHits") or 1)                   # `GetNumberConstant(0x2f)`
    profile = str(consts.get("damageProfile") or "")          # `GetDamageProfileOrDefault(0x13)`
    mn = ability_var(SEEKER_MISSILE_FREQUENCY_LOCK_ID, "minDmg", level,
                     multiplier_pct=multiplier_pct) or 0      # `ConfigVar(0xc, stateSel)`
    mx = ability_var(SEEKER_MISSILE_FREQUENCY_LOCK_ID, "maxDmg", level,
                     multiplier_pct=multiplier_pct) or 0      # `ConfigVar(0xd, stateSel)`
    amount = RandomAmount(Const(int(mn)), Const(int(mx)), rng=state.rng)
    attack = AttackWithAbilityDamage(Target(), profile, amount, is_melee=None, hits=hits,
                                     source_ref=Caster(), native_operation="ability")
    remove = RemoveEffect(SEEKER_LOCK_AIMING, Caster())
    return op_and(attack, remove)


def _seeker_missile_attack_behaviour(state: "State", unit_id: int, entities, ectx):
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[1127]` -- la phase 2, declenchee par le noeud
    `TriggerAbility` du `Triggered()` d'`APendingAttackEffect` (`triggers/pending_attack.py`).

    `unit_id` = l'unite declenchee (l'ATTAQUANT) ; `entities` = l'`AbilityEntities` reconstitue par
    le noeud, ou `Caster()` est l'attaquant et `Target()` le porteur de l'effet 1123. Le tirage du
    `RandomAmount` et l'attaque se font DANS `ectx`, donc sur le MEME `state.rng` que le reste du
    tour -- c'est ce qui rend le flux MT comparable au natif."""
    target = getattr(entities, "target", None)
    tid = target.get("id") if isinstance(target, dict) or hasattr(target, "get") else None
    level, mult = _seeker_snapshot_state(state, tid, unit_id)
    seeker_missile_frequency_lock_attack_tree(state, level, mult).execute(entities, ectx)
    # LES ETAGES du coup, pas seulement son total : sans eux une divergence de degat ne se
    # decompose pas et on en serait reduit a fitter le scalaire. C'est exactement ce qui a rendu
    # visible le `x1.15` du `Markerlight` (`per_hit` avant block vs `total` apres).
    dmg = [{"target": p.get("target"), "total": p.get("total"),
            "etages": {k: (a or {}).get(k) for k in
                       ("base_min", "base_max", "pierce", "armor", "did_block", "rolls", "per_hit")}}
           for n, p in ectx.emitted if n == "AttackWithAbilityDamage"
           for a in [p.get("attack")]]
    return {"ability": SEEKER_MISSILE_FREQUENCY_LOCK_ID, "phase": 2, "attacker": int(unit_id),
            "carrier": tid, "level": level, "multiplier": mult, "damage": dmg}


def _seeker_snapshot_state(state: "State", carrier_id, attacker_id) -> tuple:
    """`AbilityStateFromEffect( EffectFromOwner(Target@0x60, 0x463) )` -- l'etat d'ability FIGE dans
    l'instance de 1123 portee par `carrier_id`.

    Repli sur l'etat COURANT de l'attaquant quand l'instance ne porte pas de niveau bake (effet
    hydrate d'une capture, ou pose par un chemin qui n'a pas passe `scale_from_source`). Le repli est
    DIT ici plutot que silencieux : c'est le meme arbitrage que `_source_scaling`, et dans un runner
    normalise les deux valent 50 -- la difference n'est observable que si un niveau bouge entre le
    cast et le tir."""
    if carrier_id is not None and getattr(state, "effects", None) is not None:
        for e in state.effects.by_unit.get(int(carrier_id), []):
            if e.consumed or int(e.effect_type) != SEEKER_LOCK_TARGET:
                continue
            # `abilityState` du cast : une ACTIVE, donc le slot ACTIF de l'etat bake.
            lvl = getattr(e, "active_ability_level", None)
            if lvl is None:
                lvl = getattr(e, "ability_level", None)
            if lvl is not None:
                return int(lvl), int(getattr(e, "ability_variables_multiplier", 100) or 100)
            break
    e = state.get_entity(int(attacker_id)) if attacker_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return None, 100
    return (ctx.active_ability_level,
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


TRIGGERED_ABILITY_BEHAVIOURS[SEEKER_MISSILE_ATTACK] = _seeker_missile_attack_behaviour
