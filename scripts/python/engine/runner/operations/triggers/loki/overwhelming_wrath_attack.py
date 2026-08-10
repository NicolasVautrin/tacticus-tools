"""PHASE 2 d'`OverwhelmingWrath` -- la TRIGGERED `1237`, declenchee par le `Triggered()` d'
`IdunBattle.Entities.Effects.APendingAttackEffect` (`triggers/pending_attack.py`).

POURQUOI CE MODULE EST ICI, ET PAS DANS `abilities/worldeaters.py` (#503-r3). Meme cause et meme
mesure que `loki/seeker_missile_attack.py`, dont l'en-tete porte le detail : en process FRAIS,
n'important que la chaine trigger, le registre `TRIGGERED_ABILITY_BEHAVIOURS` ne portait qu'UNE
entree (`1134`), et le noeud `TriggerAbility` rendait `dispatched: False` **en retirant l'effet
1300 quand meme**. Le deplacement supprime l'arete au lieu de la fermer.

⚠ ICI L'ARETE ETAIT GRATUITE (`worldeaters` seul NE tire PAS `registry`), donc un simple import
pour effet de bord dans `registry.py` aurait suffi -- et c'est precisement ce qu'on ne fait PAS :
la phase 2 de `1069`, elle, exigeait le deplacement (arete PORTEUSE). Traiter les deux differemment
aurait inscrit dans le port une asymetrie que rien dans le natif ne justifie : le natif ne connait
qu'une seule famille, les 20 derivees d'`APendingAttackEffect`.

================================================================================================
`...Triggered.Loki.OverwhelmingWrath_AttackAbility$$CreateBehaviour(abilityState, triggerType)`
================================================================================================
MIRROR 1:1 du decompile, build `rnca9r7q6c` :

  amount  = IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage(this, abilityState)
  profile = IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetDamageProfileOrDefault(this, 0x14)
  hits    = IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config@+0x20,
                                                                            0x2f = nrOfHits)
  target  = IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies(
                unit = Caster@DSLSelectors+0x48, unique: 1, unitSelectionType: 3 )
  return    IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage(
                caster = Caster@+0x48, targets = target, amount,
                damageProfile = Nullable(profile), hits,
                abilityOrEffect = AbilityOrEffect(this), options = <struct ZEROEE>,
                selectionType = 2 )

Il n'y a AUCUN `RemoveEffect` ici, et ce n'est pas un oubli : le retrait de l'effet 1300 appartient
au `Triggered()` d'`IdunBattle.Entities.Effects.APendingAttackEffect$$
CreateHandleTriggerAbilitiesInternal`, qui compose `TriggerAbility(...) op_BitwiseAnd
RemoveEffect(Effect@DSLSelectors+0x38)` -- deja porte par `triggers/pending_attack.py`. Contraste
LU avec la phase 2 de `1069` (`loki/seeker_missile_attack.py`), dont le `CreateBehaviour` porte SON
PROPRE `RemoveEffect(1136)` en plus.

CINQ POINTS DE FIDELITE, tous LUS :

1. `MinMaxDamage` EST CONSOMMEE ICI (contraste avec 1069, ou elle est appelee et jetee). Son corps
   entier : `DSLFormulas$$RandomAmount( GetVariableForLevel(config@+0x20, 0xc = minDmg,
   abilityState), GetVariableForLevel(config@+0x20, 0xd = maxDmg, abilityState) )` -- c'est
   exactement le mode BORNES du port (`ability_attack_params`, cles `minDmg`/`maxDmg`), pas un
   degat-node.

2. LA CONFIG EST CELLE DE L'ACTIVE 1141. `GC.ability("OverwhelmingWrath_Attack")` rend **None** --
   la triggered n'a AUCUNE entree gameconfig -- alors que `this@+0x20` est non nul au runtime.
   Meme forme, meme mesure et meme conclusion que `SeekerMissileFrequencyLock_Attack` : les
   constantes consommees sont `OverwhelmingWrath.constants`, qui portent EXACTEMENT
   `{damageProfile: "Eviscerate", nrOfHits: "2"}` -- les deux que ce behaviour lit, et les seules.
   Le site natif de cette attribution n'est pas RE'd (residu #513-r3, partage).

3. `GetDamageProfileOrDefault(0x14)` = `config.GetDamageProfile() ?? 0x14` (corps LU :
   `Nullable<DamageProfileType>.GetValueOrDefault(defaultValue)`). Le kit porte
   `damageProfile = Eviscerate`, donc le defaut `0x14` n'est JAMAIS atteint -- l'ecrire en dur
   serait un fit. Le port lit le profil du kit et ne modelise pas le defaut (meme residu #513-r2).

4. `is_melee=None` -- ET C'EST LU, PAS CHOISI. Les CINQ surcharges de
   `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` ont ete decompilees : toutes
   construisent le meme couple `IdunBattle.Entities.Behaviours.AttackDamageBehaviour` +
   `IdunBattle.Entities.Behaviours.AttackBehaviour` a partir de
   `(caster, target, amount, damageProfile, hits, abilityOrEffect, options, selectionType)`, et
   **aucune ne porte de bit melee/ranged** -- exactement le constat deja ecrit pour
   `AttackWithAbilityDamage`. Le noeud ne transporte AUCUNE nature de coup, donc
   `None` = `IsMeleeAttack` ET `IsRangedAttack` tous deux FAUX.
   ⚠ Ecrire `is_melee=True` -- ce que le porteur (Azkor, melee) et le selecteur `AdjacentEnemies`
   invitent a faire -- serait une DEDUCTION, pas une lecture. Sur ce profil precis l'axe PERCAGE
   est INERTE (`GC.damage_profile("Eviscerate")` = `{PiercingRatio: 50}` SEUL, aucun
   `ExtraPierceMelee`/`ExtraPierceRanged`), donc le choix ne se distingue QUE par les gates
   defensifs `IsRangedAttack` des cibles. Residu `#503-r5` : la contre-epreuve exige une cible
   portant un reducteur gate RANGED.

5. `multi=True` -- et c'est la DIFFERENCE STRUCTURELLE avec le cleave de #478. Ici le natif passe
   le selecteur MULTI-cibles DIRECTEMENT a `AttackWithAttackDamage`, donc **UN SEUL**
   `AttackBehaviour` porte N cibles : `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
   applique alors son `OrderBy(b__5_0)` (`if (Count > 1) targets.OrderBy(...)`). Le cleave, lui,
   enveloppe CHAQUE cible dans son propre `DSLBehaviors$$Attack` via un `Foreach` -- l'`OrderBy`
   ne s'y applique pas, d'ou son `multi=False`. Confondre les deux deplacerait la consommation RNG
   des que deux cibles sont adjacentes.

`options` est une struct ZEROEE au call-site (`local_78..local_58 = 0`) -> `HasValue = 0` : ni
`alwaysOverkilled` (+4), ni `alwaysCrit` (+5). Le port laisse `force_overkill=False`,
`force_crit=False`.

NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : `BaseTriggeredAbility`, hors `ABILITY_CLASSES`.
ASCII only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
from .....dsl.base import Const
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import AdjacentEnemies
from .....entities.triggered_ability_type import TriggeredAbilityType

if TYPE_CHECKING:                                  # pragma: no cover
    from ....state import State

#: Le NOM gameconfig de l'ACTIVE 1141 -- et c'est la config que lisent LES DEUX PHASES : la
#: TRIGGERED 1237 n'a AUCUNE entree gameconfig propre (mesure, cf. le point 2 ci-dessus).
#: DERIVE de l'enum et defini ICI plutot qu'importe d'`abilities/worldeaters.py` : ce module doit
#: rester chargeable SEUL par `dispatch/registry.py`. La phase 1 garde sa propre derivation (elle
#: en a d'autres autour), donc l'identifiant existe a DEUX endroits -- ce sont deux fois la MEME
#: expression sur le MEME enum, jamais un litteral recopie, et
#: `test_503r3_registre_trigger_peuple_offline.py` fige leur egalite pour qu'un renommage cote
#: gameconfig ne puisse pas les separer en silence.
OW_ACTIVE_ID = ActiveAbilityType.OverwhelmingWrath.name              # "OverwhelmingWrath"
OW_ATTACK = int(TriggeredAbilityType.OverwhelmingWrath_Attack)       # 0x4d5 = 1237


def overwhelming_wrath_attack_tree():
    """Arbre de `...Triggered.Loki.OverwhelmingWrath_AttackAbility$$CreateBehaviour` -- cf. l'en-tete
    du module pour les cinq points de fidelite.

    `AdjacentEnemies(Caster@+0x48, unique: 1, selectionType: 3)` est la surcharge ANCREE SUR
    L'UNITE (4 arguments : `unit, unique, selType`), la MEME que
    `RighteousRepugnanceAbility$$GetAdditionalTargets` -- pas celle qui prend un selecteur de
    TUILES. Elle se lit au call-site : le 2e argument est `*(DSLSelectors + 0x48)`, une UNITE, et
    non un `CasterTile`.

    `ability_type` = `AbilityOrEffect(this)` = la TRIGGERED **1237**, pas l'active 1141 : c'est
    elle que le natif thread comme SOURCE du coup."""
    # DIFFERE et GRATUIT : `gameconfig` n'est pas un module `engine.*`, il n'entre dans aucun cycle
    # du paquet, et le hisser ferait payer le chargement du gameconfig a tout importeur -- donc a
    # `dispatch/registry.py`, qui importe ce module pour effet de bord.
    import gameconfig as GC
    consts = (GC.ability(OW_ACTIVE_ID) or {}).get("constants") or {}
    return AttackWithAttackDamage(
        AdjacentEnemies(Caster(), Const(1)),                  # `AdjacentEnemies(Caster@+0x48, 1, 3)`
        OW_ACTIVE_ID,                                         # cf. point 2 : la config de l'ACTIVE
        str(consts.get("damageProfile") or ""),               # `GetDamageProfileOrDefault(0x14)`
        is_melee=None,                                        # cf. point 4 : le noeud ne la porte pas
        # `MinMaxDamage` = `RandomAmount(GetVariableForLevel(0xc), GetVariableForLevel(0xd))` et
        # `hits` = `GetNumberConstant(0x2f)` : les cles PAR DEFAUT du mode bornes.
        level_slot="active",
        multi=True,                                           # cf. point 5 : UN behaviour, N cibles
        ability_type=OW_ATTACK,
        force_overkill=False, force_crit=False)               # `options` = struct ZEROEE


def _overwhelming_wrath_attack_behaviour(state: "State", unit_id: int, entities, ectx):
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[1237]` -- la phase 2, declenchee par le noeud
    `TriggerAbility` du `Triggered()` d'`APendingAttackEffect` (`triggers/pending_attack.py`).

    `unit_id` = l'unite declenchee (l'ATTAQUANT = le BONDE) ; `entities` est l'`AbilityEntities`
    reconstitue par ce noeud, ou `Caster()` est l'attaquant. ⚠ Sur 1141 le porteur de l'effet 1300
    ET l'entite bondee sont TOUS DEUX le caster (`AddBondEffect(1300, targets = Caster@+0x48,
    bondedEntity = Caster@+0x48)`, LU) -- les deux slots coincident donc ici, contrairement a 1069
    ou ils designent deux unites de deux JOUEURS differents. On ne s'appuie pas sur cette
    coincidence : l'arbre lit `Caster()`, ce que le natif ecrit.

    Le tirage du `RandomAmount` et les coups se font DANS `ectx`, donc sur le MEME `state.rng` que
    le reste du tour -- c'est ce qui rend le flux MT comparable au natif."""
    overwhelming_wrath_attack_tree().execute(entities, ectx)
    # LES ETAGES du coup, pas seulement son total : sans eux une divergence ne se decompose pas et
    # on en serait reduit a fitter le scalaire (meme forme que la phase 2 de 1069).
    dmg = [{"target": p.get("target"), "total": (p.get("attack") or {}).get("total"),
            "etages": {k: (p.get("attack") or {}).get(k) for k in
                       ("base_min", "base_max", "pierce", "armor", "did_block", "did_crit",
                        # `crits` = le verdict PAR COUP (`did_crit` n'est que leur OU) et
                        # `per_hit_health` la part de PV reellement retiree : sans ces deux-la,
                        # un ecart de total ne se rattache a aucun coup nomme.
                        "crits", "rolls", "per_hit", "per_hit_health",
                        "clean_min", "clean_max", "hp_before", "hp_after")}}
           for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
    return {"ability": "OverwhelmingWrath_Attack", "phase": 2, "attacker": int(unit_id),
            "damage": dmg}


TRIGGERED_ABILITY_BEHAVIOURS[OW_ATTACK] = _overwhelming_wrath_attack_behaviour
