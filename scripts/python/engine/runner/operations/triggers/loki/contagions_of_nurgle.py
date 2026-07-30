"""`ContagionsOfNurgle` — le vecteur qui POSE le debuff d'armure de l'aura sur une unite qui
APPARAIT dedans (case-dpw).

================================================================================================
RE (decompile ghidra, build `gqfc5mff6c`)
================================================================================================

## `IdunBattleLogic.Entities.Abilities.Active.Loki.ContagionsOfNurgle_AddEffectToNewUnit_Ability`

    $$CreateTrigger =
        ( On(0x32 = UnitAdded, 1) | On(0x2e = UnitResurrected, 1) | On(0x2d = UnitRevived, 1) )
        & op_LogicalNot( AreEqual(owner@0x148, target@0x178) )
        & AreEnemies(owner@0x148, target@0x178)

    $$CreateBehaviour =
        sel = Cache( FromTrigger(target@0x178,
                                 op_LogicalNot(HasEffect(target@0x178, 0x42f, 0, 6))), 1 )
        AddEffect(0x42f = 1071, AbilityStateReference, owner@0x148, sel, <options ZERO>)
      & AddEffect(0x430 = 1072, AbilityStateReference, owner@0x148, sel, <options ZERO>)

## `IdunBattleLogic.Entities.Abilities.Active.Loki.ContagionsOfNurgle_AddEffectInitially_Ability`

    $$CreateTrigger  = OnOwnerSpecificAbilityInit(0x431)
    $$CreateBehaviour = MEME paire d'`AddEffect`, sur `Enemies(owner@0x148, ...)` filtres par
                        `NOT HasEffect(@0x180, 0x42f, 0, 6)`

## `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect`

    $$.ctor -> `ADynamicStatModifierEffect(AbilityOrEffect(0x431), stat = FixedArmor, ...)` +
               `this+0x488 = <cle de constante>` / `+0x48c = <min>` / `+0x490 = <max>`
    $$CreateActiveCondition =
        AmountIsEqualOrGreater( ContagionsOfNurgleAmount(EffectSource(effect@0x150), owner@0x148),
                                Get(this+0x48c) )
      & AmountIsEqualOrGreater( Get(this+0x490),
                                ContagionsOfNurgleAmount(...) )
    $$CalculateRange(unit) =
        `s = GetStat(unit, 0xc = TurnsStarted)` ; `s > 2 ? (s > 4 ? 3 : 2) : 1`
    $$GetMaxRange = Direct(3)

    Les DEUX instances (`IdunBattle.Core.Services.EffectsDatabase` b__14_93 / b__14_94) :
        0x42f = 1071 -> ctor(cle 0x41, min 1, max 1)                    (-20 % : UNE aura)
        0x430 = 1072 -> ctor(cle 0x42, min 2, max 0x7fffffff)           (-40 % : DEUX auras ou +)

================================================================================================
FORME DU PORT
================================================================================================
* Le vecteur `On(UnitAdded)` est cable au SPAWN (`operations/spawn.py` : `on_unit_added`), qui est
  le seul site du port ou une unite ENTRE en bataille. Les branches `UnitResurrected(0x2e)` /
  `UnitRevived(0x2d)` partagent le meme foyer -- `operations/revive.py` / `resurrect.py` peuvent
  l'appeler quand elles ramenent une unite (NON cable a ce jour : residu explicite ci-dessous).
* `AddEffectInitially` (`OnOwnerSpecificAbilityInit`) n'est PAS porte, et c'est DELIBERE : le
  runner ne rejoue pas l'init de bataille, il RECHARGE un `combatSnapshot` ou le debuff est DEJA
  cuit dans `GetStat(FixedArmor)` (mesure : `astraCreed` 6000 -> 4800) et l'effet 1071 deja
  materialise par `decisionView.effects`. Le porter re-appliquerait le -20 % une seconde fois.
* La paire `AddEffect(1071) & AddEffect(1072)` est COLLAPSEE a l'instance ACTIVE : le port pose
  celle dont la fenetre `[min, max]` contient le nombre d'auras. C'est l'observable exact --
  `decisionView.effects` de la cible ne liste que `1071` dans le montage a UNE aura (mesure
  case-dpw sur `astraSmnKell`), et le stat-layer n'applique de toute facon qu'une modification.
* La MAGNITUDE est un DELTA PLAT pre-calcule `-round(FixedArmor x |pct| / 100)` (le stat-layer du
  port applique `get_stat_modification_amount` en ADDITIF) -- MEME convention que
  `ContaminatedTileEffect`. `pct` vient des variables de TRAIT du gameconfig
  (`contagionsOfNurgleArmorOneAura` = -20, `contagionsOfNurgleArmorTwoOrMoreAuras` = -40), LUES.

RESIDUS EXPLICITES :
 * `ContagionsOfNurgleAmount` natif (`ContagionsOfNurgleAmountFormula$$Calculate` -> slot 0x93 de
   `IBattleQuery`) est COLLAPSE en « nombre de porteurs VIVANTS du trait `ContagionsOfNurgle`
   ENNEMIS de l'unite, a distance hex <= `CalculateRange(porteur)` ». Le corps natif du slot n'est
   pas lu ; ce collapse est ce que la description i2 decrit (« if they stand in two or more
   overlapping enemy auras ») et il rend le bon compte (1) sur le montage mesure.
 * L'effet n'est POSE qu'a l'apparition : il n'est ni re-evalue quand l'aura GRANDIT
   (`CalculateRange` monte a 2 puis 3), ni retire quand l'unite en SORT, ni bascule 1071 <-> 1072.
   Le natif a ce cycle de vie par sa condition ACTIVE ; le port ne materialise pas `IsActive`.
 * Les branches `UnitResurrected` / `UnitRevived` du trigger ne sont pas cablees (aucun montage).
"""
from __future__ import annotations

from typing import Optional

import hexgeo

from ....state import State
from ....components import OwnerComponent, PositionComponent, StatsComponent, UnitComponent
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import trait_var
from .....entities.stats import StatType
from .....entities.traits.unit_trait import UnitTrait

CONTAGIONS_ARMOR_REDUCTION_1 = int(EffectType.ContagionsOfNurgle_ArmorReduction1)   # 0x42f = 1071
CONTAGIONS_ARMOR_REDUCTION_2 = int(EffectType.ContagionsOfNurgle_ArmorReduction2)   # 0x430 = 1072
_TRAIT = UnitTrait.ContagionsOfNurgle.name                                          # 0x7eb = 2027

# `EffectsDatabase` b__14_93 / b__14_94 : (effectType, nom, cle de variable de trait, min, max).
# `min`/`max` = la fenetre de `CreateActiveCondition` sur le nombre d'auras.
_VARIANTS = (
    (CONTAGIONS_ARMOR_REDUCTION_1, "ContagionsOfNurgle_ArmorReduction1",
     "contagionsOfNurgleArmorOneAura", 1, 1),
    (CONTAGIONS_ARMOR_REDUCTION_2, "ContagionsOfNurgle_ArmorReduction2",
     "contagionsOfNurgleArmorTwoOrMoreAuras", 2, 0x7FFFFFFF),
)


def _pos(state: State, unit_id: int):
    e = state.get_entity(int(unit_id))
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def aura_range(state: State, carrier_id: int) -> int:
    """`IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange` --
    DELEGUE au foyer deja porte (`abilities/deathguard.contagions_of_nurgle_range`), qui est le MEME
    helper natif que celui appele statiquement par `SpawnPoxwalkersAbility$$ExecuteBehaviour`."""
    from ....abilities.deathguard import contagions_of_nurgle_range
    return contagions_of_nurgle_range(state, int(carrier_id))


def aura_carriers(state: State, unit_id: int) -> list:
    """`IdunBattleLogic.Entities.DSLFactory$$ContagionsOfNurgleAmount(source, unit)` -- COLLAPSE :
    les porteurs VIVANTS du trait `ContagionsOfNurgle` ENNEMIS de `unit_id` dont le disque de rayon
    `CalculateRange(porteur)` contient `unit_id` (cf. l'en-tete, residu explicite). Le COMPTE est
    l'`amount` de la condition active ; la LISTE donne la source de la pose (`owner@0x148`)."""
    upos = _pos(state, unit_id)
    ue = state.get_entity(int(unit_id))
    uoc = ue.get_component(OwnerComponent) if ue is not None else None
    if upos is None or uoc is None:
        return []
    out = []
    for cid, ent in state.entities.items():
        if int(cid) == int(unit_id):
            continue                                   # NOT AreEqual(owner, target)
        uc = ent.get_component(UnitComponent)
        oc = ent.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive or oc.team == uoc.team:
            continue                                   # AreEnemies(owner, target)
        sc = ent.get_component(StatsComponent)
        traits = (getattr(sc.ctx, "traits", None) or ()) if sc is not None else ()
        if _TRAIT not in traits:
            continue
        cpos = _pos(state, cid)
        if cpos is None:
            continue
        if hexgeo.distance(cpos, upos) <= aura_range(state, cid):
            out.append(int(cid))
    return out


def _variant_for(count: int):
    """L'instance ACTIVE = celle dont la fenetre `[min, max]` de `CreateActiveCondition` contient
    `count` (1071 a UNE aura, 1072 a DEUX ou plus). None hors aura."""
    for etype, name, key, lo, hi in _VARIANTS:
        if lo <= count <= hi:
            return etype, name, key
    return None


def apply_on_unit_added(state: State, unit_id: int) -> Optional[dict]:
    """Vecteur `On(UnitAdded)` de `ContagionsOfNurgle_AddEffectToNewUnit_Ability` : si l'unite qui
    vient d'entrer en bataille se tient dans >= 1 aura Contagion ENNEMIE, pose le debuff d'armure
    correspondant (`-20 %` / `-40 %` du `FixedArmor` COURANT, delta plat).

    Gate `NOT HasEffect(target, 0x42f, 0, 6)` du selecteur natif : aucune re-pose. No-op strict si
    l'unite n'est dans aucune aura, si elle n'a pas de stats, ou si son armure est nulle."""
    if state.effects is None:
        return None
    e = state.get_entity(int(unit_id))
    if e is None:
        return None
    if state.effects.has_effect(int(unit_id), effect_type=CONTAGIONS_ARMOR_REDUCTION_1) or \
            state.effects.has_effect(int(unit_id), effect_type=CONTAGIONS_ARMOR_REDUCTION_2):
        return None
    carriers = aura_carriers(state, unit_id)
    n = len(carriers)
    variant = _variant_for(n)
    if variant is None:
        return None
    etype, name, key = variant
    pct = trait_var("ContagionsOfNurgle", key)
    sc = e.get_component(StatsComponent)
    if sc is None or sc.ctx is None or pct is None:
        return None
    armor = int(sc.ctx.stat(StatType.FIXED_ARMOR) or 0)
    if armor <= 0:
        return None
    # `ADynamicStatModifierEffect` : -X % du stat COURANT, materialise en DELTA PLAT (le stat-layer
    # du port applique `get_stat_modification_amount` en ADDITIF). `pct` est NEGATIF au gameconfig.
    value = -round(armor * abs(int(pct)) / 100)
    from ...effects import AddEffectOperation           # lazy : evite le cycle triggers <-> effects
    # `source` = `owner@0x148` du natif = le PORTEUR de l'aura (l'`EffectSource` que relit
    # `CreateActiveCondition`). Plusieurs porteurs -> le premier de l'enumeration (le natif pose une
    # instance PAR porteur declencheur ; la fenetre `[min,max]` n'en laisse qu'une active).
    eff = AddEffectOperation.execute(state, source=(carriers[0] if carriers else None),
                                     target=int(unit_id), effect_type=etype,
                                     name=name, value=value)
    if eff is None:
        return None
    return {"effect": name, "unit": int(unit_id), "auras": n, "armor_before": armor,
            "armor_delta": value, "carriers": carriers}
