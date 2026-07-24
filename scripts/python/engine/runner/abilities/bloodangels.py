"""Abilities Blood Angels -- SavageEchoes (1230, Cezare `bloodTerminator`).

Module DEDIE (org native = 1 classe par ability, `Abilities.Active.Loki.*` ; `loki/` et `behaviours.py`
deja > seuil de split). RE ghidra gqfc5mff6c (VA citees). Case-220 §6.12 (docs/rl/case-220/blood-angels.md).

`SavageEchoesAbility.ExecuteBehaviour @181204660` (MIRROR du DECOMPILE) :
    Execute( op_BitwiseAnd( op_BitwiseAnd(
        SetCache(cache),                                                                  # prime la memoisation
        AttackWithAttackDamage(Self@0x148, Target@0x178,
            GetDamage = Sum( MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                             Multiply( Get(GetVariableForLevel(config, 8 = extraDmg)),
                                       Count(CanAddUnit(AdjacentTiles(Self@0x148))) ) ),   # +extraDmg x free-tiles
            GetDamageProfile = Eviscerate, nrOfHits = ArmoriumCherubAbility.GetHits = GetNumberConstant(0x2f)=4) ),
        If( cache = Cache(HealthPctIsBelowOrEqual(Caster@0x160, ConfigConst(0x4f = healthPct = 50))),
            Heal(Self@0x148, Self@0x148, Get(GetVariableForLevel(config, 0x1d = hp)),
                 HealBehaviourOptions.ForRegenerate) ) ) )                                 # self-heal SI HP<=50%

Attaque MELEE (attackRangeType=Melee), 4 coups Eviscerate (PiercingRatio 50), degat = bornes minDmg/maxDmg
PLUS un bonus FLAT `extraDmg x count(tuiles adjacentes LIBRES du caster)` sur chaque coup. Si le HP du caster
etait <= 50% de son MaxHealth AVANT l'attaque, il se soigne de `hp` (variable per-niveau). REUTILISE
`ArmoriumCherubAbility.GetHits` (handler 1014) -- meme patron structurel (attaque multi-coups + volet).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import AbilityTrigger
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_and, If
from ...entities.selectors import Target, Caster, CanAddUnit, AdjacentTiles
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ..components import HealthComponent, StatsComponent
from .base import ActiveAbility
from .behaviours import entities_from_state, AttackWithAttackDamage, Heal

if TYPE_CHECKING:
    from ..state import State


def _caster_level_mult(state: "State", caster_id: int):
    """`(active_ability_level, AbilityVariablesMultiplierPercentage)` du caster -- MEME source que
    `ability_attack_params` (`GetVariableForLevel(config, idx, level)` scale par le multiplier rarete)."""
    ce = state.get_entity(caster_id)
    sc = ce.get_component(StatsComponent) if ce is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return level, mult


class _RegenerateCondition(AbilityTrigger):
    """Predicat FIGE (booleen pre-attaque) = fold de `SetCache(Cache(HealthPctIsBelowOrEqual(Caster@0x160,
    ConfigConst(0x4f = healthPct)))) @181204bd0`. Le natif MEMOISE (`SetCache`) la condition au DEBUT du tree
    (avant l'attaque) et le `If(cache, Heal)` relit la valeur cachee -> on capture le booleen PRE-attaque
    dans `execute_behaviour` (plumbing pur, precedent SpiritLeech `SetCache`/`Cache` foldes). `Stat
    PercentageIsBelowOrEqualAbilityTrigger.ShouldTrigger @180ef5d60` = `(current/max) <= (healthPct/100)` en
    Fix64 (stat Health=5, variant 0=Current, variant 2=Maximum), equivalent entier EXACT
    `100*current <= healthPct*max` (cf. `_regenerate_precondition`)."""
    __slots__ = ("value",)

    def __init__(self, value: bool):
        self.value = bool(value)

    def should_trigger(self, ctx) -> bool:
        return self.value


def _regenerate_precondition(state: "State", caster_id: int) -> bool:
    """`HealthPctIsBelowOrEqual(Caster, ConfigConst(healthPct)) @180ef5d60` evalue PRE-attaque : True ssi
    `current_hp / max_hp <= healthPct / 100`. Le HP courant vit dans `HealthComponent` (muté par les degats)
    -- `get_stat(Health, Current)` rendrait le HP INIT du snapshot (unit_context.py:108), donc on lit
    `HealthComponent` directement (== `SetHealth` @stats.py). Comparaison entiere exacte : pour des PV entiers,
    la division Fix64 `current/max` ne bascule JAMAIS `<= healthPct/100` autrement que `100*current <=
    healthPct*max` (granularite `1/(2*max)` >> precision Fix64 `2^-32`) -- egalite au bord `2*current == max`
    rendue Fix64 = 0.5 exact -> `<=` vrai."""
    ce = state.get_entity(caster_id)
    hc = ce.get_component(HealthComponent) if ce is not None else None
    if hc is None or hc.hp is None or not hc.hp_max:
        return False
    pct = ability_var("SavageEchoes", "healthPct", is_constant=True)   # ConfigConst(0x4f) = 50
    if pct is None:
        return False
    return 100 * int(hc.hp) <= int(pct) * int(hc.hp_max)


def savage_echoes_heal_amount(entities, ectx) -> int:
    """`Get(GetVariableForLevel(config, 0x1d = hp))` -- montant du `Heal(Self, ForRegenerate)`. `hp` = variable
    per-niveau (rarity-affected -> multiplier applique par `ability_var`). Montant FIXE (independant de
    l'attaque -- contraste avec le lifesteal `PercentageOf(LastAttackDamageMade)` de SpiritLeech)."""
    caster = (entities.caster or {}).get("id")
    if caster is None or ectx.state is None:
        return 0
    level, mult = _caster_level_mult(ectx.state, caster)
    return int(ability_var("SavageEchoes", "hp", level, multiplier_pct=mult) or 0)


def savage_echoes_tree(regenerate: bool, damage_override):
    """Arbre de `SavageEchoesAbility.ExecuteBehaviour @181204660` (id 1230, `bloodTerminator` Cezare -- MIRROR
    du DECOMPILE ; cf. en-tete module). Port (plain `Execute`, PAS `ExecuteAtomic`) :
        op_and( AttackWithAttackDamage(Target(), "SavageEchoes", "Eviscerate", melee, damage_override),
                If( _RegenerateCondition(regenerate), Heal(Caster(), savage_echoes_heal_amount) ) )
    - `SetCache`/`Cache(HealthPctIsBelowOrEqual)` FOLDES : la memoisation fige la condition HP<=50% PRE-attaque
      -> capturee en amont (`regenerate`), relue par le `If` (plumbing pur, precedent SpiritLeech).
    - le degat `Sum(MinMax, Multiply(extraDmg, count))` = un bonus FLAT `extraDmg x free-adjacent-tiles` ajoute
      a chaque coup, porte via `damage_override` (mirror `SpiritLeech.GetAttackDamage @181209dd0`, meme point
      d'injection : le natif passe la node de degat calculee a `AttackWithAttackDamage`).
    - `native_factory="attack"` (defaut) : l'`ExecuteBehaviour` @18120487b appelle `DSLFactory.AttackWith
      AttackDamage @180de9fb0` (famille ATTACK, 2 tirages/coup a cc=0 -- verifie par XREFS, cas rngcrit-1202) ;
      IDENTIQUE au template ArmoriumCherub (@1811b417d -> @180de9fb0). Bit-exact multi-coups by construction.
    L'ordre `op_and` (Attack PUIS Heal) n'insere aucun tirage RNG hors l'attaque (Heal deterministe) ->
    l'ordre RNG de l'attaque est inchange."""
    attack = AttackWithAttackDamage(Target(), "SavageEchoes", "Eviscerate", is_melee=True,
                                    damage_override=damage_override, native_factory="attack")
    heal = Heal(Caster(), savage_echoes_heal_amount)                  # Heal(Self, Self, Get(hp), ForRegenerate)
    return op_and(attack, If(_RegenerateCondition(regenerate), heal))


class SavageEchoesAbility(ActiveAbility):
    """`SavageEchoesAbility.ExecuteBehaviour @181204660` (id 1230, `bloodTerminator` « Cezare »).

    Le behaviour est l'arbre DSL `savage_echoes_tree` : la feuille `AttackWithAttackDamage` emet la MEME
    Operation d'attaque d'ability (4 coups Eviscerate melee, degat + `extraDmg x free-tiles`) que le pipeline
    combat porte, et le `If(RegenCond, Heal)` pose un self-heal SI le HP etait <= 50% AVANT l'attaque (fige
    pre-attaque, mirror SetCache). Deterministe hors l'attaque -> bit-exact BY CONSTRUCTION vs l'imperatif."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SavageEchoes)   # 1230
    ABILITY_ID = "SavageEchoes"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        level, mult = _caster_level_mult(state, caster_id)
        extra = int(ability_var("SavageEchoes", "extraDmg", level, multiplier_pct=mult) or 0)
        # `Count(CanAddUnit(AdjacentTiles(Self@0x148)))` = nb de tuiles adjacentes LIBRES (walkable + inoccupees)
        # du caster. Evalue au timing GetDamage (== l'appel unique de `damage_override` par le leaf, AVANT la
        # boucle de coups) : `AttackDamageBehaviour.GetDamage @180fbb250` calcule les bornes UNE fois par cible
        # (Calculate index 2=Min / 3=Max) -> `flat = extraDmg x count` CONSTANT sur les 4 coups (== modele
        # bornes-figees deja valide bit-exact multi-coups). `entities` (LiveUnit) porte l'occupation PRE-attaque.
        free_sel = CanAddUnit(AdjacentTiles(Caster()))

        def damage_override(_st, _caster, _target, bmin, bmax):
            count = len(free_sel.evaluate(entities))
            flat = extra * count
            return bmin + flat, bmax + flat

        regenerate = _regenerate_precondition(state, caster_id)       # SetCache : fige HP<=50% pre-attaque
        savage_echoes_tree(regenerate, damage_override).execute(entities, ectx)
        main = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        heal_amount, heals = 0, []
        for name, p in ectx.emitted:
            if name == "Heal":
                heal_amount = p.get("amount") or 0
                heals = p.get("heals") or []
        free_tiles = len(free_sel.evaluate(entities))                 # diag (POST-attaque : occupation a pu bouger)
        return {"ability": "SavageEchoes", "caster": caster_id, "target": target_id,
                "main_attack": main, "regenerate": regenerate, "extra_per_tile": extra,
                "free_tiles_after": free_tiles, "heal_amount": heal_amount, "heals": heals, "dsl": True}
