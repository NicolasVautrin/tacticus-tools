"""PHASE 2 de `SolarAtomizer` -- la TRIGGERED `1297`, declenchee par le `Triggered()` d'
`IdunBattle.Entities.Effects.APendingAttackEffect` (`triggers/pending_attack.py`). #894-r2.

Meme emplacement et meme cause que `loki/the_lantern_attack.py`, `loki/lions_wrath_attack.py`,
`loki/overwhelming_wrath_attack.py` et `loki/seeker_missile_attack.py` : une ability TRIGGERED vit
avec les triggers, pour que `TRIGGERED_ABILITY_BEHAVIOURS[1297]` soit peuple des que
`dispatch/registry.py` est charge, sans dependre d'`abilities/handler.py` (cliquet
`test_503r3_registre_trigger_peuple_offline.py`, dont le PERIMETRE est DERIVE de
`PENDING_ATTACK_EFFECTS`).

================================================================================================
`...Triggered.Loki.SolarAtomizer_PendingAttackAbility$$CreateBehaviour(abilityState, triggerType)`
================================================================================================
MIRROR 1:1 du decompile, build `t6dpr4k06g` :

  marked  = DSLSelectors$$EntitiesWithAnyEffect( entities   = <DSLSelectors+0x18> = AllTiles,
                                                 effectType = 0x55c = 1372 SolarAtomizer_PendingTarget,
                                                 effectTarget = 6 = EffectTargetType.Both )
  cache   = DSLSelectors$$Cache( marked, matchAbilityEntities = 1 )
  targets = DSLSelectors$$Enemies( of = Caster@DSLSelectors+0x48,
                                   entities = DSLSelectors$$Units( cache, 1, 3 ),
                                   selectionType = 3 = OnlyAliveAndTargetable )
  atk     = DSLBehaviors$$AttackWithAttackDamage(
                caster        = Owner@DSLSelectors+0x30,
                target        = targets,
                amount        = BaseTriggeredAbility$$MinMaxDamage(this, abilityState),
                damageProfile = Nullable(BaseTriggeredAbility$$GetDamageProfileOrDefault(this, 8)),
                hits          = BaseTriggeredAbility$$GetHits(this),
                abilityOrEffect = AbilityOrEffect(this),
                options       = <struct ZEROEE>,
                selectionType = 2 )
  rm      = DSLBehaviors$$RemoveEffect( selector = cache, effectType = Nullable(0x55c), null )
  return DSLBehaviors$$AtomicGroup( 0x2a = GroupType.Ability_AtomicGroup, rm op_BitwiseAnd atk )

TROIS ECARTS AVEC SON VOISIN LE PLUS PROCHE (`TheLantern`), tous LUS -- ne pas recopier le voisin :

1. **`AttackWithAttackDamage`, PAS `AttackWithAbilityDamage`.** Deux familles d'operation natives
   distinctes (`AttackDamageBehaviour` -> `AttackDamageOperation.ExecuteHit` contre
   `AbilityDamageBehaviour` -> `AbilityDamageOperation.ExecuteHits`), qui ne consomment PAS le meme
   nombre de tirages par coup (le resolve slot-8 de la premiere en gaspille un a `cc = 0`). Le port
   le porte par `native_factory = "attack"`.
2. **Un `Units(...)` s'intercale entre le cache et `Enemies`.** `TheLantern` passe le cache de
   TUILES directement a `Enemies` (dont le selecteur convertit lui-meme tuile -> occupant) ; ici le
   natif ecrit explicitement `Units(cache, 1, 3)`. On l'ecrit, on ne le collapse pas.
3. **Le profil par defaut est `8`, pas `0x10`.** `GetDamageProfileOrDefault(this, 8)` --
   la config porte `damageProfile = Melta`, donc le defaut n'est jamais atteint ; l'ecrire en dur
   serait un fit.

DEUX POINTS DE FIDELITE PARTAGES AVEC LE VOISIN, tous deux LOAD-BEARING :

* **LA MARQUE VIT SUR DES TUILES, ET ELLE EST RELUE AU MOMENT DU TIR.** `EntitiesWithAnyEffect`
  part d'`AllTiles`, pas d'une liste d'unites figee au cast : ce sont les occupants COURANTS des
  tuiles marquees qui prennent le coup.
* **LE `Cache` EST LOAD-BEARING, ET L'ORDRE `rm & atk` AUSSI.** Le `RemoveEffect` s'execute AVANT
  l'attaque (le decompile ecrit `op_BitwiseAnd(rm, atk)`), donc sans memo l'`EntitiesWithAnyEffect`
  du second membre rendrait un ensemble DEJA VIDE et personne ne serait frappe.

LA CONFIG EST CELLE DE L'ACTIVE 1174. `GC.ability("SolarAtomizer_PendingAttack")` rend **None** --
la triggered n'a aucune entree gameconfig, meme forme et meme conclusion que les quatre voisines
(residu #513-r3 pour le site natif de l'attribution, partage). La config LUE est
`constants = {nrOfHits: 3, damageProfile: Melta, cooldownTurns: 1}` et `variables = {minDmg, maxDmg}`.

NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : `BaseTriggeredAbility`, hors `ABILITY_CLASSES`.
ASCII only.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.effects import RemoveEffect
from ....abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
from ....components import StatsComponent
from .....dsl.base import Const
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.behaviours import AtomicGroup, op_and
from .....entities.effect_target_type import EffectTargetType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import RandomAmount
from .....entities.selectors.accessors import Owner
from .....entities.selectors.geometry import Cache, EntitiesWithAnyEffect
from .....entities.selectors.tiles import AllTiles
from .....entities.selectors.units import Enemies, Units
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_selection_type import UnitSelectionType
from .....streams.group_type import GroupType

if TYPE_CHECKING:                                  # pragma: no cover
    from ....state import State

#: Le NOM gameconfig de l'ACTIVE 1174 -- la config que lisent LES DEUX PHASES. DERIVE de l'enum et
#: defini ICI plutot qu'importe d'`abilities/admec.py` : ce module doit rester chargeable SEUL par
#: `dispatch/registry.py` (meme discipline que `TL_ACTIVE_ID`).
SA_ACTIVE_ID = ActiveAbilityType.SolarAtomizer.name                    # "SolarAtomizer"
SA_ATTACK = int(TriggeredAbilityType.SolarAtomizer_PendingAttack)      # 0x511 = 1297
SA_PENDING_TARGET = int(EffectType.SolarAtomizer_PendingTarget)        # 0x55c = 1372
SA_PENDING_ATTACK = int(EffectType.SolarAtomizer_PendingAttack)        # 0x55b = 1371
#: 3e argument LU de `DSLSelectors$$Enemies(of, entities, selectionType)` ET de `$$Units(.., .., 3)`.
_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)             # 3


def solar_atomizer_attack_tree(state: "State", level: Optional[int], multiplier_pct: int):
    """Arbre de `...Triggered.Loki.SolarAtomizer_PendingAttackAbility$$CreateBehaviour`.

    Construit A CHAQUE declenchement : le `Cache` porte un memo d'instance, et le reutiliser d'un
    tour a l'autre figerait la zone du PREMIER tir.

    `level`/`multiplier_pct` = l'`abilityState` que `BaseTriggeredAbility$$MinMaxDamage` consomme --
    resolu par l'appelant sur l'ATTAQUANT (cf. `_solar_atomizer_state`)."""
    # DIFFERE et GRATUIT : `gameconfig` n'est pas un module `engine.*`, il n'entre dans aucun cycle
    # du paquet, et le hisser ferait payer le chargement du gameconfig a tout importeur -- donc a
    # `dispatch/registry.py`, qui importe ce module pour effet de bord. (Meme raison, meme forme
    # que `the_lantern_attack_tree`.)
    import gameconfig as GC
    consts = (GC.ability(SA_ACTIVE_ID) or {}).get("constants") or {}
    hits = int(consts.get("nrOfHits") or 1)                # `BaseTriggeredAbility$$GetHits`
    profile = str(consts.get("damageProfile") or "")       # `GetDamageProfileOrDefault(8)`
    mn = ability_var(SA_ACTIVE_ID, "minDmg", level, multiplier_pct=multiplier_pct) or 0
    mx = ability_var(SA_ACTIVE_ID, "maxDmg", level, multiplier_pct=multiplier_pct) or 0
    # `EntitiesWithAnyEffect(AllTiles, 1372, EffectTargetType.Both)` : le 3e argument natif
    # (`effectTarget`) n'est pas un parametre du noeud porte -- il interroge `ctx.tile_has_effect`,
    # qui ne distingue pas owner/target sur une entite-TUILE (les deux valent la tuile elle-meme).
    _ = EffectTargetType.Both                              # 6 -- litteral natif, QUALIFIE
    cache = Cache(EntitiesWithAnyEffect(AllTiles(), [SA_PENDING_TARGET]))
    # `Units(cache, 1, 3)` PUIS `Enemies(Caster@+0x48, .., 3)` -- ECRIT, pas collapse (ecart 2).
    targets = Enemies(Units(cache, selection_type=_SELECTION), selection_type=_SELECTION)
    amount = RandomAmount(Const(int(mn)), Const(int(mx)), rng=state.rng)
    atk = AttackWithAttackDamage(targets, SA_ACTIVE_ID, profile, is_melee=None, hits=hits,
                                 amount=amount,
                                 source_ref=Owner(),       # `Owner@DSLSelectors+0x30`
                                 multi=True,               # le selecteur resout N unites
                                 native_factory="attack",  # `AttackWithAttackDamage` (ecart 1)
                                 ability_type=SA_ATTACK)
    rm = RemoveEffect(SA_PENDING_TARGET, cache)
    # `AtomicGroup(0x2a = GroupType.Ability_AtomicGroup, rm op_BitwiseAnd atk)` -- l'ORDRE est celui
    # du decompile. Le noeud porte ne prend PAS le `groupType` : `AtomicGroup.execute` inline son
    # enfant (RE #201), le groupe de presentation n'ayant aucun effet d'etat.
    _ = GroupType.Ability_AtomicGroup                      # 0x2a = 42 -- litteral natif, QUALIFIE
    return AtomicGroup(op_and(rm, atk))


def _solar_atomizer_state(state: "State", attacker_id) -> tuple:
    """L'`abilityState` que `BaseTriggeredAbility$$MinMaxDamage(this, abilityState)` consomme.

    Le natif passe l'`abilityState` recu par `CreateBehaviour`, c'est-a-dire celui de l'ability
    DECLENCHEE sur l'unite declenchee -- le port lit donc le slot ACTIF de l'ATTAQUANT
    (`SolarAtomizer_PendingAttack` n'a aucune entree gameconfig : la config lue est celle de
    l'active 1174, dont le niveau vit dans ce slot). Meme forme que `_the_lantern_state`.

    Attaquant sans `StatsComponent` -> niveau `None` / multiplicateur 100 : `ability_var` repond
    alors ce que la config a a l'index 0, aucune valeur inventee."""
    e = state.get_entity(int(attacker_id)) if attacker_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return None, 100
    return (ctx.active_ability_level,
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def _solar_atomizer_attack_behaviour(state: "State", unit_id: int, entities, ectx):
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[1297]` -- la phase 2, declenchee par le noeud
    `TriggerAbility` du `Triggered()` d'`APendingAttackEffect` (`triggers/pending_attack.py`).

    `unit_id` = l'unite declenchee (l'ATTAQUANT) ; `entities` est l'`AbilityEntities` reconstitue
    par ce noeud, ou `Caster()` et `Owner()` sont l'attaquant. PORTEUR et ATTAQUANT sont ICI LA
    MEME UNITE -- le cast pose `1371` sur le caster lui-meme (`AddEffect`, pas `AddBondEffect`) --
    mais on ne collapse pas les deux slots pour autant : c'est le foyer qui les resout."""
    level, mult = _solar_atomizer_state(state, unit_id)
    tree = solar_atomizer_attack_tree(state, level, mult)
    tree.execute(entities, ectx)
    dmg = [{"target": p.get("target"), "total": p.get("total"),
            "etages": {k: (a or {}).get(k) for k in
                       ("base_min", "base_max", "pierce", "armor", "did_block", "rolls", "per_hit",
                        "hp_before", "hp_after")}}
           for n, p in ectx.emitted if n == "AttackWithAttackDamage"
           for a in [p.get("attack")]]
    removed = [{"target": p.get("target"), "removed": p.get("removed")}
               for n, p in ectx.emitted if n == "RemoveEffect"]
    return {"ability": "SolarAtomizer_PendingAttack", "phase": 2, "attacker": int(unit_id),
            "level": level, "multiplier": mult, "damage": dmg, "removed": removed}


TRIGGERED_ABILITY_BEHAVIOURS[SA_ATTACK] = _solar_atomizer_attack_behaviour
