"""`Abilities.Active.Loki.FinalJusticeAbility` (@18121f180) — attaque de MORT de worldKharn (trait
`FinalJustice`). Cf. `loki/__init__.py` pour le regroupement « Loki »."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, HealthComponent
from ....abilities.behaviours import UseActiveAbility, entities_from_state
from ....damage_model import select_weapon_pierce, attacker_modifiers
from .....entities.stats import StatType
from .....entities.effects import hits_bonus_from_effects
from .....entities.selectors import Caster, Target
from .....services.damage_prediction import get_attack_prediction
from .....utilities import damage_composite
from .....weights import load as _load_weights
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _adjacent_enemies

# Cache des poids d'utilité (BC `Utilities` — statiques, cf. project_ai_weights_in_battle_config) pour le
# tri de cible FinalJustice (chargé une fois depuis la BC JSON sur disque ; seules KillUnit/OverkillUnit
# sont lues — les poids DamageDealt 80/20 sont des Fix64 codés en dur dans `DamageUtility.cctor`).
_DAMAGE_UTILITY_WEIGHTS = None


def _damage_utility_weights():
    global _DAMAGE_UTILITY_WEIGHTS
    if _DAMAGE_UTILITY_WEIGHTS is None:
        _DAMAGE_UTILITY_WEIGHTS = _load_weights()
    return _DAMAGE_UTILITY_WEIGHTS


def _normal_attack_health_range(state: State, owner_id: int):
    """Plage de dégât SANTÉ (min,max) du TOTAL de l'attaque normale mêlée de l'owner, PRÉ-ARMURE — mirror
    de la `DamagePrediction` que `SortUnitsByDamageUtilitySelector.Select`@180ef4960 bâtit par cible
    (`FUN_18002c910` scénario 0x25, profil `NormalAttackDamage`). La prédiction IA d'attaque normale est
    PRÉ-ARMURE (`armor=0` ; cf. en-tête `services/damage_prediction`) ⇒ le dégât est INDÉPENDANT de la
    cible → calculé UNE fois. Inclut les ×modifiers d'effet de l'attaquant (RapidAssault…) et les hits
    d'arme+effet. Renvoie (dmin, dmax) du total, ou None si stats indispo."""
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    ahc = owner.get_component(HealthComponent)
    _pierce, _ranged, whits = select_weapon_pierce(ctx, 1)             # dist=1 → arme mêlée
    mods, active = attacker_modifiers(state, owner_id, ahc.hp if ahc else None, is_ranged=False)
    hits = max(1, whits + ctx.stat(StatType.EXTRA_HITS) + hits_bonus_from_effects(active))
    pred = get_attack_prediction(
        target_current_health=0, initial_damage=int(ctx.stat(StatType.ATTACK)), hits=hits,
        profile_type=0, armor=0, pierce_pct=100, mods=mods, spread_pct=20)    # PRÉ-ARMURE (armor=0)
    return (pred.accurate_health_damage.min, pred.accurate_health_damage.max)


def _finaljustice_target(state: State, owner_id: int) -> Optional[int]:
    """`ValidNormalAttackTargets`@180e01b40 → `SortUnitsByDamageUtility`@180dfb8f0 → MEILLEURE cible.

    Tri natif RE LECTURE INTÉGRALE (`SortUnitsByDamageUtilitySelector.Select`@180ef4960 +
    `FinalJusticeAbility.CreateBehaviour`@18121ed00) : pour chaque cible normal-attaquable, bâtit une
    `DamagePrediction` de l'attaque normale → score `UtilityDecider.CalculateUtility(UtilityDefinition
    0x22 = 34 = composite Damage, cible, prediction)` → Dict cible→util → `OrderBy(util via lambda
    <Select>b__0)` → 1ʳᵉ. Le lambda `<Select>b__0`@180efec40 renvoie **`Fix64.op_UnaryNegation(util)`**
    (= −util) ⇒ `OrderBy(−util)` = tri DÉCROISSANT par utilité ⇒ la 1ʳᵉ cible = utilité **MAX**.
    ⇒ FinalJustice frappe l'**argmax du composite Damage(34)** = DamageDealt(35)+KillUnit(36)+
    OverkillUnit(37) (`engine.utilities.damage_composite`). Kharn = mêlée ⇒ cibles = ennemis adjacents.

    Prédiction PRÉ-ARMURE (`_normal_attack_health_range`) ⇒ dégât identique pour toutes les cibles ; le
    classement dépend des PV courants/max + flags kill/overkill PAR cible (kill = dmg ≥ PV). Tie-break :
    `OrderBy` natif STABLE → ordre source `ValidNormalAttackTargets` ; approximé ici par id croissant
    (itération `sorted(cands)` + argmax STRICT). Bouclier non modélisé (`shieldBefore=0`, comme le reste
    du moteur — TODO). Fallback PV-bas si la prédiction est indispo (pas de stats)."""
    cands = _adjacent_enemies(state, owner_id)
    if not cands:
        return None

    def _hp(eid: int) -> int:
        e = state.get_entity(eid)
        h = e.get_component(HealthComponent) if e is not None else None
        return int(h.hp) if (h is not None and h.hp is not None) else (1 << 30)

    rng_pred = _normal_attack_health_range(state, owner_id)
    if rng_pred is None:                                   # pas de stats → proxy PV-bas (fallback)
        return min(cands, key=lambda eid: (_hp(eid), eid))

    dmin, dmax = rng_pred
    wt = _damage_utility_weights()
    best = None
    best_util = None
    for eid in sorted(cands):                              # ordre déterministe (tie-break id croissant)
        e = state.get_entity(eid)
        hc = e.get_component(HealthComponent) if e is not None else None
        hp = int(hc.hp) if (hc is not None and hc.hp is not None) else 0
        max_hp = int(hc.hp_max) if (hc is not None and hc.hp_max) else hp
        shield = 0                                         # bouclier non modélisé (rare ; TODO)
        eff_min = max(0, dmin - shield)
        eff_max = max(0, dmax - shield)
        pred = {"healthDmgMin": eff_min, "healthDmgMax": eff_max,
                # rawHealthDmg* = plage NON capée (mirror @0x24/@0x28) : `OverkillUnit` faithful via over-shoot
                # (dmg >= 2*PV), comme `SortUnitsByDamageUtility` natif — ici eff_* SONT déjà bruts (#84).
                "rawHealthDmgMin": eff_min, "rawHealthDmgMax": eff_max,
                "hpBefore": hp, "shieldBefore": shield,
                "killSure": hp > 0 and eff_min >= hp,      # WillBeKill (dmg min ≥ PV)
                "kill": hp > 0 and eff_max >= hp}          # MightBeKill (dmg max ≥ PV)
        util = damage_composite(pred, max_hp, wt)
        if best_util is None or util > best_util:          # argmax (strict → 1er id en cas d'égalité)
            best_util = util
            best = eid
    return best


def _finaljustice_attack(state: State, owner_id: int) -> Optional[dict]:
    """Behaviour FinalJustice (CreateBehaviour@18121ed00), MIGRÉ en ARBRE DSL (#149 slice-22) :
    `UseActiveAbility(Self@0x148, <best>, UnitNormalAttackType)` = UNE attaque NORMALE (chemin
    `AttackDamageOperation.execute`, déjà bit-exact) sur la meilleure cible normal-attaquable. Le sélecteur
    AI-target `SortUnitsByDamageUtility(ValidNormalAttackTargets)` (kind S lourd, chevauche le playbook)
    reste IMPÉRATIF (`_finaljustice_target`) et est COLLAPSÉ en `Target()` (== ThunderousAssault
    `Units(Cache(First(Nearest(...))))`). Le gate natif `Count(validTargets)>0 AND NOT TargetIsOverkilled`
    + le nœud `Inform` sont portés dans `matches()` (déjà fidèle). Bit-exact vs l'ancien corps impératif
    BY CONSTRUCTION : la feuille `UseActiveAbility` appelle le MÊME `AttackDamageOperation.execute(owner,
    best, 20)`. No-op si pas de cible. (L'owner est `alive=False` — death-rattle ; l'attaque s'exécute
    quand même.)"""
    target = _finaljustice_target(state, owner_id)
    if target is None:
        return {"trait": "FinalJustice", "owner": owner_id, "target": None}
    ectx = ExecutionContext(state=state, rng=state.rng)
    UseActiveAbility(Caster(), Target()).execute(entities_from_state(state, owner_id, target), ectx)
    res = next((p for (n, p) in ectx.emitted if n == "UseActiveAbility"), {}).get("attack")
    return {"trait": "FinalJustice", "owner": owner_id, "target": target, "attack": res}


class FinalJusticeAbility(TriggeredAbility):
    """`FinalJusticeAbility` (@18121f180 CreateTrigger / @18121ed00 CreateBehaviour) — attaque de MORT de
    worldKharn (trait `FinalJustice`).

    CreateTrigger = `OnPreDeath & OwnerIsTarget` — l'owner EST l'unité qui meurt (slot 0x178=dying).
    Behaviour = `UseActiveAbility(UnitNormalAttackType, best)` sur la meilleure cible normal-attaquable
    (`ValidNormalAttackTargets` -> `SortUnitsByDamageUtility`), GATÉ `Count(validTargets)>0 AND NOT
    TargetIsOverkilled`. ⇒ en mourant, Kharn porte UNE attaque normale sur l'ennemi le plus rentable —
    SAUF si le coup fatal l'a OVERKILL (dmg >= 2*PV ; cf. `is_overkill`). `fire_on_death` car l'owner est
    déjà `alive=False` au moment du dispatch MORT (bypass du gate vivant, comme `CanGetAbilityTrigger`)."""
    event_id = EventTriggerType.PreUnitDeath
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.dying_id != self.owner_id:                 # OwnerIsTarget (owner = unité mourante)
            return False
        if ev.overkill:                                  # NOT TargetIsOverkilled
            return False
        return _finaljustice_target(state, self.owner_id) is not None   # Count(validTargets) > 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _finaljustice_attack(state, self.owner_id)
