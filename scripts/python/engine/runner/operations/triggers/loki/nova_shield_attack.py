"""PHASE 2 de `NovaShield` (1194) -- la TRIGGERED `1325`, declenchee par le `Triggered()` d'
`IdunBattle.Entities.Effects.APendingAttackEffect` (`triggers/pending_attack.py`). #895-r4.

Meme emplacement et meme cause que `loki/solar_atomizer_attack.py`, `loki/the_lantern_attack.py`,
`loki/lions_wrath_attack.py`, `loki/overwhelming_wrath_attack.py` et `loki/seeker_missile_attack.py`
: une ability TRIGGERED vit avec les triggers, pour que `TRIGGERED_ABILITY_BEHAVIOURS[1325]` soit
peuple des que `dispatch/registry.py` est charge, sans dependre d'`abilities/handler.py` (cliquet
`test_503r3_registre_trigger_peuple_offline.py`, dont le PERIMETRE est DERIVE de
`PENDING_ATTACK_EFFECTS`).

TANT QUE CETTE PHASE MANQUAIT, un boss qui avait caste `NovaShield` n'infligeait RIEN au tour
suivant -- en silence, exactement comme `#491-r1` et `#503-r1` avant leur port.

================================================================================================
`...Triggered.Loki.NovaShield_AttackAbility$$CreateBehaviour(abilityState, triggerType)`
================================================================================================
MIRROR 1:1 du decompile, build `t6dpr4k06g` :

  marked  = DSLSelectors$$Cache(
                DSLSelectors$$EntitiesWithAnyEffect( entities     = <DSLSelectors+0x18> AllTiles,
                                                     effectTypes  = { 0x587 },
                                                     effectTarget = 6 = EffectTargetType.Both ),
                matchAbilityEntities = 1 )
  targets = DSLSelectors$$Enemies( of            = Caster@<DSLSelectors+0x48>,
                                   entities      = DSLSelectors$$Units(marked, unique = 1, 3),
                                   selectionType = 3 = OnlyAliveAndTargetable )
  atk     = DSLBehaviors$$AttackWithAttackDamage(
                caster          = Owner@<DSLSelectors+0x30>,
                target          = targets,
                amount          = BaseTriggeredAbility$$MinMaxDamage(this, abilityState),
                damageProfile   = Nullable(BaseTriggeredAbility$$GetDamageProfileOrDefault(this, 5)),
                hits            = BaseTriggeredAbility$$GetHits(this),
                abilityOrEffect = AbilityOrEffect( <ActiveAbilityType> 0x4aa = 1194 NovaShield ),
                options         = <struct ZEROEE>,
                selectionType   = 2 )
  rm      = DSLBehaviors$$RemoveEffect( selector = marked, effectType = Nullable(0x587),
                                        replaceableEffectType = null )
  return    AbilityBehaviour$$op_BitwiseAnd( rm , atk )          # <-- PAS d'AtomicGroup

QUATRE POINTS DE FIDELITE, tous LUS :

1. **L'ORDRE `rm & atk`, ET LE `Cache` QUI LE REND VIVABLE.** Le decompile CONSTRUIT l'attaque en
   premier mais l'appelle en SECOND argument de l'`op_BitwiseAnd` : `op_BitwiseAnd(rm, atk)`. Le
   `RemoveEffect` part donc AVANT le coup, et sans le memo du `Cache` l'`EntitiesWithAnyEffect` du
   second membre rendrait un ensemble DEJA VIDE -- personne ne serait frappe. Meme forme, meme
   raison que chez `SolarAtomizer`.

2. **PAS D'`AtomicGroup`, ET C'EST UN ECART LU AVEC `SolarAtomizer`.** Le voisin enveloppe son
   `rm & atk` dans `DSLBehaviors$$AtomicGroup(0x2a, ...)` ; ici le `return` est l'`op_BitwiseAnd`
   nu. Recopier le voisin ajouterait un groupe que le natif n'a pas.

3. **`abilityOrEffect` EST L'`ActiveAbilityType` 1194, PAS LA TRIGGERED 1325.** L'overload appele
   est `IdunBattle.Core.AbilityOrEffect$$op_Implicit(<ActiveAbilityType>)`, et l'immediat charge
   dans `edx` juste avant le `call` est `0xaa 0x04` -- **`mov edx, 0x4aa` = 1194** (lu aux OCTETS,
   le decompilateur ne montre pas cet argument). C'est l'axe d'ATTRIBUTION du degat (`Effect_Type`)
   et la cle des bonus de degat par ability : s'y tromper est silencieux sur le total et faux sur
   l'attribution.
   ⚠ QUALIFICATION D'ENUM, parce que l'ordinal ne discrimine PAS : `1194` est
   `ActiveAbilityType.NovaShield`, mais aussi `TriggeredAbilityType.LordOfTempests` et
   `EffectType.TheLantern_PendingAttack`. Le NOM est le seul canal ou la faute serait visible.

4. **UN `Units(...)` S'INTERCALE entre le cache et `Enemies`** -- ecrit par le natif, pas collapse
   (meme ecart que `SolarAtomizer` a avec `TheLantern`, qui passe le cache de TUILES directement).

LA CONFIG EST CELLE DE L'ACTIVE 1194. `GC.ability("NovaShield_Attack")` et
`GC.ability("NovaShield_PendingAttack")` rendent **None** tous les deux -- la triggered n'a aucune
entree gameconfig, meme forme et meme conclusion que les cinq voisines (residu #513-r3 pour le site
natif de l'attribution, partage). La config LUE est
`constants = {damageProfile: Particle, nrOfHits: 6, nrOfRounds: 1, cooldownTurns: 2}`,
`variables = {blockChance, maxDmg, minDmg, shieldHp}` -- donc le defaut `5` de
`GetDamageProfileOrDefault` n'est JAMAIS atteint, et l'ecrire en dur serait un fit.

`is_melee = False` : `attackRangeType` de 1194 = `"Ranged"` au gameconfig, et c'est la CONFIG qui
decide -- `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetAttackRangeType` rend
`config@+0x20 -> +0x20`, c'est-a-dire l'`attackRangeType` de la config lue (celle de l'ACTIVE).
Meme canal que celui mesure pour `OverwhelmingWrath` (`Melee` -> `is_melee=True`, #503-r5).

NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : `BaseTriggeredAbility` n'a **aucun `.ctor`** dans
`ghidra/functions.tsv` et ne prend pas de `TargetingOptions` -- le couple `TargetingOptions..ctor` +
`AActiveAbility..ctor(this, &opts, attackType)` est propre a `AActiveAbility`. La classe est hors
`ABILITY_CLASSES` : il n'y a rien a renseigner, et c'est un RESULTAT, pas un oubli.

`get_AllowForDeadOwner` : **non declare** -> FAUX herite de `BaseTriggeredAbility`
(`data/symbols/<build>/metadata/allow_for_dead_owner.tsv` ne porte aucune entree `Nova*`). Rien a
poser -- ce n'est pas une `TriggeredAbility` du registre de dispatch, elle est appelee par le noeud
`TriggerAbility` du `Triggered()` de l'effet.

ASCII only.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.effects import RemoveEffect
from ....abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
from ....components import ActiveAbilitiesComponent, StatsComponent
from .....dsl.base import Const
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.behaviours import op_and
from .....entities.effect_target_type import EffectTargetType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import RandomAmount
from .....entities.selectors.geometry import Cache, EntitiesWithAnyEffect
from .....entities.selectors.tiles import AllTiles
from .....entities.selectors.units import Enemies, Units
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_selection_type import UnitSelectionType

if TYPE_CHECKING:                                  # pragma: no cover
    from ....state import State

#: Le NOM gameconfig de l'ACTIVE 1194 -- la config que lisent LES DEUX PHASES. DERIVE de l'enum et
#: defini ICI plutot qu'importe d'`abilities/tau.py` : ce module doit rester chargeable SEUL par
#: `dispatch/registry.py` (meme discipline que `SA_ACTIVE_ID` / `TL_ACTIVE_ID`).
NS_ACTIVE_ID = ActiveAbilityType.NovaShield.name                      # "NovaShield"
#: L'ability DECLENCHEE. ⚠ **`TriggeredAbilityType`, pas `EffectType`** : `1325` nomme
#: `GazeOfMagnus_PendingAttack` dans l'enum des effets.
NS_ATTACK = int(TriggeredAbilityType.NovaShield_Attack)               # 0x52d = 1325
#: La MARQUE posee sur les TUILES par la phase 1 (`AddEffect(0x587, ..., tiles, null)`).
NS_PENDING_TARGET = int(EffectType.NovaShield_PendingTarget)          # 0x587 = 1415
#: L'effet PORTEUR, pose sur le caster par `AddBondEffect(0x586, ...)` -- c'est lui qui declenche.
NS_PENDING_ATTACK = int(EffectType.NovaShield_PendingAttack)          # 0x586 = 1414
#: L'`abilityOrEffect` du noeud d'attaque -- l'ACTIVE, cf. point 3 de l'en-tete.
NS_ATTRIBUTION = int(ActiveAbilityType.NovaShield)                    # 0x4aa = 1194
#: 3e argument LU de `DSLSelectors$$Enemies(of, entities, selectionType)` ET de `$$Units(.., .., 3)`.
_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)            # 3


def _nova_ability_state(state: "State", caster_id) -> tuple:
    """L'`abilityState` que `BaseTriggeredAbility$$MinMaxDamage(this, abilityState)` consomme --
    l'**`AbilityState` PER-ABILITY** de l'ACTIVE 1194 sur l'attaquant.

    ⚠ **CE N'EST PAS LE CANAL GLOBAL, ET LA DIFFERENCE EST UN FACTEUR MESURE.** La chaine native
    est LUE de bout en bout : `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility`
    appelle `IdunBattle.Entities.UnitExtensions$$GetAbilityState(entity, <TriggeredAbilityType>)`,
    qui passe par `StaticBattleRules.TriggeredAbility$$GetActiveAbilityUsedForConfig` puis par
    l'overload `GetAbilityState(unit, <ActiveAbilityType>)` -- lequel parcourt
    `ActiveAbilityComponent.<+0x20>` et rend le couple du PREMIER slot dont `<+0x44>` vaut l'active.
    Sur `tauBossRiptide`, le canal GLOBAL (`StatsComponent.ctx`) rend `level=0, mult=100` parce que
    `combatSnapshot.unitConfig` vaut `{"error": "config null"}` pour un npc, la ou le canal
    per-ability rend `level=55, multiplier=200` -- soit un facteur 137 sur `shieldHp` (#895).

    ⚠ **DUPLICATION NOMMEE** : ce corps est celui d'`engine/runner/abilities/tau.py::_ability_scaling`,
    qui est DEJA generique (il prend son `ability_type` en parametre). Il n'est pas importe ici
    parce que ce module doit rester chargeable SEUL par `dispatch/registry.py` -- importer
    `abilities/tau.py` y ferait entrer tout le registre d'actives. Le bon geste est de HISSER ce
    foyer dans un module que la cascade des triggers ne re-entre pas ; il est nomme comme residu
    plutot que fait ici, parce que `abilities/tau.py` est un fichier partage.

    Repli sur le canal GLOBAL quand le composant per-ability n'est pas seede (il exige
    `allAbilities: true` a la capture) -- exactement le repli du foyer d'origine."""
    e = state.get_entity(int(caster_id)) if caster_id is not None else None
    if e is None:
        return (0, 100)
    comp = e.get_component(ActiveAbilitiesComponent)
    ab = comp.get(NS_ATTRIBUTION) if comp is not None else None
    if ab is not None and ab.level is not None:
        return (int(ab.level), int(ab.multiplier if ab.multiplier is not None else 100) or 100)
    sc = e.get_component(StatsComponent)
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return (level, mult)


def nova_shield_attack_tree(state: "State", level: Optional[int], multiplier_pct: int):
    """Arbre de `...Triggered.Loki.NovaShield_AttackAbility$$CreateBehaviour` -- cf. l'en-tete.

    Construit A CHAQUE declenchement : le `Cache` porte un memo d'instance, et le reutiliser d'un
    tour a l'autre figerait la zone du PREMIER tir."""
    # DIFFERE et GRATUIT : `gameconfig` n'est pas un module `engine.*`, il n'entre dans aucun cycle
    # du paquet, et le hisser ferait payer le chargement du gameconfig a tout importeur -- donc a
    # `dispatch/registry.py`, qui importe ce module pour effet de bord. (Meme raison, meme forme
    # que `solar_atomizer_attack_tree`.)
    import gameconfig as GC
    consts = (GC.ability(NS_ACTIVE_ID) or {}).get("constants") or {}
    hits = int(consts.get("nrOfHits") or 1)                # `BaseTriggeredAbility$$GetHits`
    profile = str(consts.get("damageProfile") or "")       # `GetDamageProfileOrDefault(5)`
    mn = ability_var(NS_ACTIVE_ID, "minDmg", level, multiplier_pct=multiplier_pct) or 0
    mx = ability_var(NS_ACTIVE_ID, "maxDmg", level, multiplier_pct=multiplier_pct) or 0
    # `EntitiesWithAnyEffect(AllTiles, 1415, EffectTargetType.Both)` : le 3e argument natif
    # (`effectTarget`) n'est pas un parametre du noeud porte -- il interroge `ctx.tile_has_effect`,
    # qui ne distingue pas owner/target sur une entite-TUILE (les deux valent la tuile elle-meme).
    _ = EffectTargetType.Both                              # 6 -- litteral natif, QUALIFIE
    cache = Cache(EntitiesWithAnyEffect(AllTiles(), [NS_PENDING_TARGET]))
    # `Units(marked, 1, 3)` PUIS `Enemies(Caster@+0x48, .., 3)` -- ECRIT, pas collapse (point 4).
    targets = Enemies(Units(cache, selection_type=_SELECTION), selection_type=_SELECTION)
    amount = RandomAmount(Const(int(mn)), Const(int(mx)), rng=state.rng)
    atk = AttackWithAttackDamage(targets, NS_ACTIVE_ID, profile,
                                 is_melee=False,           # `attackRangeType = "Ranged"` (LU)
                                 hits=hits, amount=amount,
                                 multi=True,               # le selecteur resout N unites
                                 native_factory="attack",  # `AttackWithAttackDamage`
                                 ability_type=NS_ATTRIBUTION)   # 1194, PAS 1325 -- cf. point 3
    rm = RemoveEffect(NS_PENDING_TARGET, cache)
    # `op_BitwiseAnd(rm, atk)` NU -- pas d'`AtomicGroup` (point 2), ordre `rm` d'abord (point 1).
    return op_and(rm, atk)


def _nova_shield_attack_behaviour(state: "State", unit_id: int, entities, ectx):
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[1325]` -- la phase 2, declenchee par le noeud
    `TriggerAbility` du `Triggered()` d'`APendingAttackEffect` (`triggers/pending_attack.py`).

    `unit_id` = l'unite declenchee (l'ATTAQUANT) ; `entities` est l'`AbilityEntities` reconstitue
    par ce noeud, ou `Caster()` et `Owner()` sont l'attaquant. PORTEUR, SOURCE et BONDE sont ICI LA
    MEME UNITE -- la phase 1 pose `AddBondEffect(0x586, AbilityStateReference, source = Owner@+0x30,
    targets = Owner@+0x30, bondedEntity = Owner@+0x30, options = <ZERO>)`, les TROIS slots valent
    `Owner` -- mais on ne collapse pas pour autant : c'est le foyer `pending_attack` qui les resout,
    et l'ecart serait INVISIBLE sur ce porteur et faux ailleurs."""
    level, mult = _nova_ability_state(state, unit_id)
    nova_shield_attack_tree(state, level, mult).execute(entities, ectx)
    # LES ETAGES du coup, pas seulement son total (meme diag que les cinq autres phases 2).
    dmg = [{"target": p.get("target"), "total": p.get("total"),
            "etages": {k: (a or {}).get(k) for k in
                       ("base_min", "base_max", "pierce", "armor", "did_block", "rolls", "per_hit",
                        "hp_before", "hp_after")}}
           for n, p in ectx.emitted if n == "AttackWithAttackDamage"
           for a in [p.get("attack")]]
    removed = [{"target": p.get("target"), "removed": p.get("removed")}
               for n, p in ectx.emitted if n == "RemoveEffect"]
    return {"ability": "NovaShield_Attack", "phase": 2, "attacker": int(unit_id),
            "level": level, "multiplier": mult, "damage": dmg, "removed": removed,
            # LA VENTILATION BRUTE des noms emis : un `damage: []` ne dit pas si rien n'a frappe ou
            # si ce lecteur cherche le mauvais nom. Ce compte-ci tranche.
            "emis": sorted({n for n, _ in ectx.emitted})}


TRIGGERED_ABILITY_BEHAVIOURS[NS_ATTACK] = _nova_shield_attack_behaviour
