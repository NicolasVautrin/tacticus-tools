"""PHASE 2 de `TheLantern` -- la TRIGGERED `1167`, declenchee par le `Triggered()` d'
`IdunBattle.Entities.Effects.APendingAttackEffect` (`triggers/pending_attack.py`). #1030.

Meme emplacement et meme cause que `loki/lions_wrath_attack.py`, `loki/overwhelming_wrath_attack.py`
et `loki/seeker_missile_attack.py` : une ability TRIGGERED vit avec les triggers, pour que
`TRIGGERED_ABILITY_BEHAVIOURS[1167]` soit peuple des que `dispatch/registry.py` est charge, sans
dependre d'`abilities/handler.py` (cliquet `test_503r3_registre_trigger_peuple_offline.py`, dont le
PERIMETRE est DERIVE de `PENDING_ATTACK_EFFECTS`).

================================================================================================
`...Triggered.Loki.TheLantern_AttackAbility$$CreateBehaviour(abilityState, triggerType)`
================================================================================================
MIRROR 1:1 du decompile, build `rnca9r7q6c` :

  marked  = DSLSelectors$$EntitiesWithAnyEffect( entities   = <DSLSelectors+0x18> = AllTiles,
                                                 effectType = 0x4ab = 1195 TheLantern_PendingTarget,
                                                 effectTarget = 6 = EffectTargetType.Both )
  cache   = DSLSelectors$$Cache( marked, matchAbilityEntities = 1 )
  targets = DSLSelectors$$Enemies( of = Caster@DSLSelectors+0x48, entities = cache,
                                   selectionType = 3 = OnlyAliveAndTargetable )
  atk     = DSLBehaviors$$AttackWithAbilityDamage(
                caster        = Owner@DSLSelectors+0x30,
                target        = targets,
                amount        = BaseTriggeredAbility$$MinMaxDamage(this, abilityState),
                damageProfile = Nullable(BaseTriggeredAbility$$GetDamageProfileOrDefault(this, 0x10)),
                hits          = BaseTriggeredAbility$$GetHits(this),
                abilityOrEffect = AbilityOrEffect(this),
                selectionType = 2 )
  rm      = DSLBehaviors$$RemoveEffect( selector = cache,
                                        effectType = Nullable(0x4ab = 1195),
                                        replaceableEffectType = null )
  return DSLBehaviors$$AtomicGroup( 0x2a = GroupType.Ability_AtomicGroup, rm op_BitwiseAnd atk )

QUATRE POINTS DE FIDELITE, tous LUS :

1. **LA MARQUE VIT SUR DES TUILES, ET ELLE EST RELUE AU MOMENT DU TIR.** `EntitiesWithAnyEffect`
   part d'`AllTiles`, pas d'une liste d'unites figee au cast : ce sont les occupants COURANTS des
   tuiles marquees qui prennent le coup. Une unite qui SORT de la zone y echappe, une unite qui y
   ENTRE la prend. C'est le seul volet de ce kit qui exige une confrontation sur DEUX tours.

2. **LE `Cache` EST LOAD-BEARING, ET L'ORDRE `rm & atk` AUSSI.** Le `RemoveEffect` s'execute AVANT
   l'attaque (le decompile ecrit `op_BitwiseAnd(rm, atk)`), donc sans memo l'`EntitiesWithAnyEffect`
   du second membre rendrait un ensemble DEJA VIDE et personne ne serait frappe. Le `Cache` natif
   (`matchAbilityEntities = 1`) fige l'ensemble a sa PREMIERE evaluation ; le port le mirrore par
   le meme noeud, et l'arbre est construit UNE FOIS par declenchement pour que le memo soit frais.

3. **`Enemies` PART D'ENTITES-TUILES.** `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$Select`
   passe par `IdunBattle.DSL.TargetsSelector$$SelectUniqueUnits` -> `$$SelectUnit`, dont la premiere
   ligne est `if (IsUnitFoot(entity) || IsTile(entity)) entity = GetUnit(entity, state);` : la
   conversion tuile -> occupant appartient au SELECTEUR, pas a l'arbre. Le port de `Enemies` ne la
   faisait pas (elle rendait `[]` sur des ids de tuile) -- reparee dans
   `entities/selectors/units.py` avec cette tranche, pas contournee ici par un `Units(...)` que le
   natif n'ecrit pas.

4. **LA CONFIG EST CELLE DE L'ACTIVE 1094.** `GC.ability("TheLantern_Attack")` rend **None**
   (mesure) -- la triggered n'a aucune entree gameconfig. Meme forme, meme mesure et meme
   conclusion que `SeekerMissileFrequencyLock_Attack`, `OverwhelmingWrath_Attack` et
   `TheLionsWrath_PendingAttack` (residu #513-r3 pour le site natif de l'attribution, partage).
   `GetDamageProfileOrDefault(this, 0x10)` = `config.GetDamageProfile() ?? 0x10` : la config porte
   `damageProfile = Energy`, donc le defaut n'est jamais atteint -- l'ecrire en dur serait un fit.

`is_melee=None` -- ET C'EST LU, PAS CHOISI, exactement comme pour la phase 2 de `1069` : les QUATRE
surcharges de `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` prennent
`(caster, target, amount, damageProfile, hits, abilityOrEffect, [options,] selectionType)` et
**aucune ne porte de bit melee/ranged**. Le kit declare `attackRangeType = "Ranged"` -- c'est la
portee de l'ABILITY (elle sert au ciblage), pas la nature du COUP sur ce vecteur.

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
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.behaviours import AtomicGroup, op_and
from .....entities.effect_target_type import EffectTargetType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import RandomAmount
from .....entities.selectors.accessors import Owner
from .....entities.selectors.geometry import Cache, EntitiesWithAnyEffect
from .....entities.selectors.tiles import AllTiles
from .....entities.selectors.units import Enemies
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_selection_type import UnitSelectionType
from .....streams.group_type import GroupType

if TYPE_CHECKING:                                  # pragma: no cover
    from ....state import State

#: Le NOM gameconfig de l'ACTIVE 1094 -- la config que lisent LES DEUX PHASES (cf. point 4).
#: DERIVE de l'enum et defini ICI plutot qu'importe d'`abilities/deathguard.py` : ce module doit
#: rester chargeable SEUL par `dispatch/registry.py` (meme discipline que `LW_ACTIVE_ID`).
TL_ACTIVE_ID = ActiveAbilityType.TheLantern.name                       # "TheLantern"
TL_ATTACK = int(TriggeredAbilityType.TheLantern_Attack)                # 0x48f = 1167
TL_PENDING_TARGET = int(EffectType.TheLantern_PendingTarget)           # 0x4ab = 1195
TL_PENDING_ATTACK = int(EffectType.TheLantern_PendingAttack)           # 0x4aa = 1194
#: 3e argument LU de `DSLSelectors$$Enemies(of, entities, selectionType)`.
_ENEMIES_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


def the_lantern_attack_tree(state: "State", level: Optional[int], multiplier_pct: int):
    """Arbre de `...Triggered.Loki.TheLantern_AttackAbility$$CreateBehaviour` -- cf. l'en-tete.

    Construit A CHAQUE declenchement : le `Cache` porte un memo d'instance (`_cached`), et le
    reutiliser d'un tour a l'autre figerait la zone du PREMIER tir.

    `level`/`multiplier_pct` = l'`abilityState` que `BaseTriggeredAbility$$MinMaxDamage` consomme --
    resolu par l'appelant sur l'ATTAQUANT (cf. `_the_lantern_state`)."""
    # DIFFERE et GRATUIT : `gameconfig` n'est pas un module `engine.*`, il n'entre dans aucun cycle
    # du paquet, et le hisser ferait payer le chargement du gameconfig a tout importeur -- donc a
    # `dispatch/registry.py`, qui importe ce module pour effet de bord. (Meme raison, meme forme
    # que `seeker_missile_frequency_lock_attack_tree`.)
    import gameconfig as GC
    consts = (GC.ability(TL_ACTIVE_ID) or {}).get("constants") or {}
    hits = int(consts.get("nrOfHits") or 1)                # `BaseTriggeredAbility$$GetHits`
    profile = str(consts.get("damageProfile") or "")       # `GetDamageProfileOrDefault(0x10)`
    mn = ability_var(TL_ACTIVE_ID, "minDmg", level, multiplier_pct=multiplier_pct) or 0
    mx = ability_var(TL_ACTIVE_ID, "maxDmg", level, multiplier_pct=multiplier_pct) or 0
    # `EntitiesWithAnyEffect(AllTiles, 1195, EffectTargetType.Both)` : le 3e argument natif
    # (`effectTarget`) n'est pas un parametre du noeud porte -- il interroge `ctx.tile_has_effect`,
    # qui ne distingue pas owner/target sur une entite-TUILE (les deux valent la tuile elle-meme).
    _ = EffectTargetType.Both                              # 6 -- litteral natif, QUALIFIE
    cache = Cache(EntitiesWithAnyEffect(AllTiles(), [TL_PENDING_TARGET]))
    targets = Enemies(cache, selection_type=_ENEMIES_SELECTION)
    amount = RandomAmount(Const(int(mn)), Const(int(mx)), rng=state.rng)
    atk = AttackWithAbilityDamage(targets, profile, amount, is_melee=None, hits=hits,
                                  source_ref=Owner(),      # `Owner@DSLSelectors+0x30`
                                  multi=True,              # le selecteur resout N unites
                                  native_operation="ability",
                                  ability_type=TL_ATTACK)
    rm = RemoveEffect(TL_PENDING_TARGET, cache)
    # `AtomicGroup(0x2a = GroupType.Ability_AtomicGroup, rm op_BitwiseAnd atk)` -- l'ORDRE est celui
    # du decompile (cf. point 2). Le noeud porte ne prend PAS le `groupType` : `AtomicGroup.execute`
    # inline son enfant (RE #201), le groupe de presentation n'ayant aucun effet d'etat. Le litteral
    # natif est QUALIFIE ci-dessous plutot qu'ecrit en dur nulle part.
    _ = GroupType.Ability_AtomicGroup                      # 0x2a = 42 -- litteral natif, QUALIFIE
    return AtomicGroup(op_and(rm, atk))


def _the_lantern_state(state: "State", attacker_id) -> tuple:
    """L'`abilityState` que `BaseTriggeredAbility$$MinMaxDamage(this, abilityState)` consomme.

    ⚠ CONTRASTE LU avec la phase 2 de `1069` : celle-ci va chercher l'etat FIGE dans l'effet
    (`AbilityStateFromEffect(EffectFromOwner(...))`) ; ICI le natif passe l'`abilityState` recu par
    `CreateBehaviour`, c'est-a-dire celui de l'ability DECLENCHEE sur l'unite declenchee. Le port lit
    donc le slot ACTIF de l'ATTAQUANT (`TheLantern_Attack` n'a aucune entree gameconfig, cf. point 4
    de l'en-tete : la config lue est celle de l'active 1094, dont le niveau vit dans ce slot).

    Attaquant sans `StatsComponent` -> niveau `None` / multiplicateur 100 : `ability_var` repond
    alors ce que la config a a l'index 0, aucune valeur inventee (meme degradation qu'ailleurs)."""
    e = state.get_entity(int(attacker_id)) if attacker_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return None, 100
    return (ctx.active_ability_level,
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def _the_lantern_attack_behaviour(state: "State", unit_id: int, entities, ectx):
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[1167]` -- la phase 2, declenchee par le noeud
    `TriggerAbility` du `Triggered()` d'`APendingAttackEffect` (`triggers/pending_attack.py`).

    `unit_id` = l'unite declenchee (l'ATTAQUANT) ; `entities` est l'`AbilityEntities` reconstitue par
    ce noeud, ou `Caster()` et `Owner()` sont l'attaquant. ⚠ Contrairement a 1069 et 1217, PORTEUR et
    ATTAQUANT sont ICI LA MEME UNITE (le cast pose `1194` sur le caster lui-meme) -- on ne collapse
    pas pour autant les deux slots : c'est le foyer qui les resout, comme pour 1141.

    Le tirage du `RandomAmount` et les coups se font DANS `ectx`, donc sur le MEME `state.rng` que le
    reste du tour."""
    level, mult = _the_lantern_state(state, unit_id)
    tree = the_lantern_attack_tree(state, level, mult)
    tree.execute(entities, ectx)
    # LES ETAGES du coup, pas seulement son total (meme diag que les trois autres phases 2).
    dmg = [{"target": p.get("target"), "total": p.get("total"),
            "etages": {k: (a or {}).get(k) for k in
                       ("base_min", "base_max", "pierce", "armor", "did_block", "rolls", "per_hit",
                        "hp_before", "hp_after")}}
           for n, p in ectx.emitted if n == "AttackWithAbilityDamage"
           for a in [p.get("attack")]]
    removed = [{"target": p.get("target"), "removed": p.get("removed")}
               for n, p in ectx.emitted if n == "RemoveEffect"]
    return {"ability": "TheLantern_Attack", "phase": 2, "attacker": int(unit_id),
            "level": level, "multiplier": mult, "damage": dmg, "removed": removed}


TRIGGERED_ABILITY_BEHAVIOURS[TL_ATTACK] = _the_lantern_attack_behaviour
