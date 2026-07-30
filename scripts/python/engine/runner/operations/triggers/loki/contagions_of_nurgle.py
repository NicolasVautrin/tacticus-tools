"""`ContagionsOfNurgle` — le vecteur qui POSE le debuff d'armure de l'aura sur une unite qui
APPARAIT dedans (case-dpw), et le CYCLE DE VIE de ce debuff (case-cvc).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================

## `IdunBattleLogic.Entities.Abilities.Active.Loki.ContagionsOfNurgle_AddEffectToNewUnit_Ability`

    $$CreateTrigger =
        ( On(0x32 = UnitAdded, 1) | On(0x2e = UnitResurrected, 1) | On(0x2d = UnitRevived, 1) )
        & op_LogicalNot( AreEqual(owner@0x148, target@0x178) )
        & AreEnemies(owner@0x148, target@0x178)

    ⚠ ORDINAUX RE-DERIVES du build COURANT (`data/symbols/<build>/frida/enums.tsv`,
    `IdunBattle.DSL.EventTriggerType`), PAS recopies : l'enum a ete RENUMEROTE et les valeurs
    heritees de case-dpw (`0x33`/`0x2f`/`0x2e`) designent aujourd'hui `PreUnitFled` /
    `UnitMemberDeath` / `UnitResurrected`. Les citer sans re-deriver, c'est nommer un AUTRE
    evenement -- cf. le balayage #292 (728 citations corrigees).

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

    $$.ctor -> `AStatModifierEffect(AbilityOrEffect(0x431), 0, 0, 1, 1)` +
               `this+0x488 = <cle de constante>` / `+0x48c = <min>` / `+0x490 = <max>`
    $$CreateActiveCondition =
        AmountIsEqualOrGreater( ContagionsOfNurgleAmount(EffectSource(effect@0x150), Owner@0x30),
                                Get(this+0x48c = min) )
      & AmountIsEqualOrGreater( Get(this+0x490 = max),
                                ContagionsOfNurgleAmount(...) )
    $$CalculateRange(unit) =
        `s = GetStat(unit, 0xc = TurnsStarted)` ; `s > 2 ? (s > 4 ? 3 : 2) : 1`
    $$GetMaxRange = Direct(3)

    Les DEUX instances (`IdunBattle.Core.Services.EffectsDatabase` b__14_93 / b__14_94) :
        0x42f = 1071 -> ctor(cle 0x41, min 1, max 1)                    (-20 % : UNE aura)
        0x430 = 1072 -> ctor(cle 0x42, min 2, max 0x7fffffff)           (-40 % : DEUX auras ou +)

## `ContagionsOfNurgleAmount` -- RESOLU (case-cvc), plus de collapse

`IdunBattle.Entities.Triggers.ContagionsOfNurgleAmountFormula$$Calculate`, lu verbatim :

    entity = <selecteur team>.SelectSingle(entities) ;  if (entity == null) return 0
    teamId = EntityExtensions.GetCurrentTeamId(entity, state)
    target = <selecteur unit>.SelectSingle(entities) ;  if (target == null) return 0
    return battleQuery.<slot 0x95>(0x42f, teamId, target, returnFirst: false)

et le slot 0x95 est `IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount` (meme signature
`(effectType, team, target, returnFirst)`), DEJA porte par case-224. Deux consequences MESURABLES
par rapport au collapse precedent :
  * comparateur **INCLUSIF** `dist <= GetCurrentRange(porteur)` (la version d'EQUIPE).
    ⚠ Le predicat par-UNITE (`IsInUnitContagionsOfNurgleAura`) est INCLUSIF **lui aussi** -- il
    construit un `AmountIsEqualOrGreaterAbilityTrigger`, pas l'`AmountIsGreaterAbilityTrigger` que
    suggere le nom (DEDUPLIQUE) de son `.ctor` (#293). Les deux versions ont donc le MEME rayon
    effectif -- cf. `entities/triggers.py::IsInUnitAura` ;
  * filtre d'appartenance `GetCurrentTeamId(porteur) == team(EffectSource)` = « porteurs ALLIES DE
    LA SOURCE de l'effet », pas « ennemis de la cible ».
Le port DELEGUE desormais (`runner/components.contagions_of_nurgle_amount`), il ne re-derive rien.

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
* La paire `AddEffect(1071) & AddEffect(1072)` est POSEE TELLE QUELLE (le collapse « une seule
  instance, celle qui est active » est DEFAIT) : les deux instances coexistent sur la cible et
  leurs fenetres DISJOINTES `[1,1]` / `[2,+inf[` font que le -20 % et le -40 % ne s'appliquent
  jamais ensemble. C'est ce qui rend la bascule 1071 <-> 1072 STRUCTURELLEMENT possible : quand le
  nombre d'auras change, ce n'est pas un effet qu'on remplace, c'est l'un qui s'active pendant que
  l'autre se desactive. L'observable reste conforme au montage a UNE aura de case-dpw
  (`decisionView.effects` de `astraSmnKell` ne liste que 1071) : le canal par DEFAUT droppe les
  effets a `IsActive == 0`, et cote port `active_effects` fait pareil via `is_active`.
* La MAGNITUDE est un DELTA PLAT pre-calcule `-round(FixedArmor x |pct| / 100)` (le stat-layer du
  port applique `get_stat_modification_amount` en ADDITIF) -- MEME convention que
  `ContaminatedTileEffect`. `pct` vient des variables de TRAIT du gameconfig
  (`contagionsOfNurgleArmorOneAura` = -20, `contagionsOfNurgleArmorTwoOrMoreAuras` = -40), LUES.
  Les DEUX valeurs sont calculees sur le MEME `FixedArmor` (celui d'avant toute pose).
* Le CYCLE DE VIE (aura qui grandit / unite qui sort / bascule) est tenu par la
  `CreateActiveCondition` de la classe d'effet (`entities/effects/loki/status.py::
  ContagionsOfNurgleArmorReductionEffect.is_active`) et par le driver
  `runner/operations/refresh_effects.refresh_stat_modifier_effects` (mirror de
  `IdunBattle.Operations.RefreshEffectsOperation`), appele ici a la pose puis par les vecteurs de
  refresh (`MoveUnitOperation` = `RefreshEffectTrigger.UnitPositionChanged`, `StartTurnOperation` =
  `RefreshEffectTrigger.TurnChanged`).

RESIDUS EXPLICITES :
 * Une instance SEEDEE depuis `decisionView.effects` n'a pas de `value` (sa contribution est deja
   cuite dans le `GetStat` capte) : elle peut donc etre RETIREE quand la condition tombe (le retrait
   se fait sous `statmod_source_key`, la cle de l'attribution du seed) mais pas RE-POSEE si la
   condition redevient vraie. Le cycle complet n'est exerce que sur une instance POSEE offline
   (summon apparaissant en bataille) -- c'est le montage de case-dpw.
 * Les branches `UnitResurrected` / `UnitRevived` du trigger ne sont pas cablees (aucun montage).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, contagions_of_nurgle_amount
from .....entities.effect_type import EffectType
from .....entities.effects.loki.status import ContagionsOfNurgleArmorReductionEffect
from .....entities.effects.magnitude import trait_var
from .....entities.stats import StatType

CONTAGIONS_ARMOR_REDUCTION_1 = int(EffectType.ContagionsOfNurgle_ArmorReduction1)   # 0x42f = 1071
CONTAGIONS_ARMOR_REDUCTION_2 = int(EffectType.ContagionsOfNurgle_ArmorReduction2)   # 0x430 = 1072

# `EffectsDatabase` b__14_93 / b__14_94 : (effectType, nom, cle de variable de trait). La FENETRE
# `[min, max]` de chaque instance vit avec la CLASSE d'effet (`CTOR_ARGS`), qui EST ce qui evalue la
# `CreateActiveCondition` -- ici on n'a besoin que de la magnitude a poser.
_VARIANTS = (
    (CONTAGIONS_ARMOR_REDUCTION_1, "ContagionsOfNurgle_ArmorReduction1",
     "contagionsOfNurgleArmorOneAura"),
    (CONTAGIONS_ARMOR_REDUCTION_2, "ContagionsOfNurgle_ArmorReduction2",
     "contagionsOfNurgleArmorTwoOrMoreAuras"),
)


def aura_range(state: State, carrier_id: int) -> int:
    """`IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange` --
    DELEGUE au foyer deja porte (`abilities/deathguard.contagions_of_nurgle_range`), qui est le MEME
    helper natif que celui appele statiquement par `SpawnPoxwalkersAbility$$ExecuteBehaviour`."""
    from ....abilities.deathguard import contagions_of_nurgle_range
    return contagions_of_nurgle_range(state, int(carrier_id))


def aura_carriers(state: State, unit_id: int) -> list:
    """Les PORTEURS d'aura Contagion, ENNEMIS de `unit_id`, dont le disque contient `unit_id`.

    ⚠ Ce n'est PAS `ContagionsOfNurgleAmount` (qui delegue a `GetInRangeAuraAmount` et compte par
    EQUIPE DE LA SOURCE -- cf. l'en-tete). Cette liste sert au seul besoin du VECTEUR DE POSE :
    choisir l'`EffectSource` (`owner@0x148` du `CreateBehaviour`, le porteur d'aura dont le trigger
    a fire). Le trigger natif est bien `AreEnemies(owner@0x148, target@0x178)`, d'ou le filtre
    ennemi ici. Le COMPTE qui decide de l'ACTIVITE, lui, passe par le foyer delegue.

    MEME etage de portee que le compte (`GetCurrentRange` via `aura_range`) et MEME comparateur
    INCLUSIF : les deux lisent `entities/effects/aura.py`."""
    import hexgeo
    from ....components import OwnerComponent, PositionComponent, UnitComponent
    from .....entities.traits.unit_trait import UnitTrait

    def _pos(uid):
        ent = state.get_entity(int(uid))
        pc = ent.get_component(PositionComponent) if ent is not None else None
        return (pc.col, pc.row) if pc is not None else None

    upos = _pos(unit_id)
    ue = state.get_entity(int(unit_id))
    uoc = ue.get_component(OwnerComponent) if ue is not None else None
    if upos is None or uoc is None:
        return []
    trait = UnitTrait.ContagionsOfNurgle.name                                    # 0x7eb = 2027
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
        if trait not in traits:
            continue
        cpos = _pos(cid)
        if cpos is None:
            continue
        if hexgeo.distance(cpos, upos) <= aura_range(state, cid):
            out.append(int(cid))
    return out


def instance_is_active(state: State, unit_id: int, name: str) -> Optional[bool]:
    """L'instance nommee `name` portee par `unit_id` est-elle ACTIVE (flag `EffectComponent.IsActive`
    ET `CreateActiveCondition`) ? Lit le MEME `unit_state` que le driver (foyer unique
    `unit_state_for_effects`, #208). `None` = l'unite ne porte pas cette instance."""
    from ....components import unit_state_for_effects
    if state.effects is None:
        return None
    us = unit_state_for_effects(state, int(unit_id))
    for e in state.effects.by_unit.get(int(unit_id), []):
        if e.name == name and isinstance(e, ContagionsOfNurgleArmorReductionEffect):
            if e.consumed or e.expired:
                return None
            return bool(e.active and e.is_active(us))
    return None


def apply_on_unit_added(state: State, unit_id: int) -> Optional[dict]:
    """Vecteur `On(UnitAdded)` de `ContagionsOfNurgle_AddEffectToNewUnit_Ability` :

        sel = Cache( FromTrigger(target@0x178, NOT HasEffect(target@0x178, 0x42f, 0, 6)), 1 )
        AddEffect(0x42f, AbilityStateReference, owner@0x148, sel, ZERO)
      & AddEffect(0x430, AbilityStateReference, owner@0x148, sel, ZERO)

    Les DEUX poses partagent le MEME selecteur cache -- le gate `NOT HasEffect(..., 0x42f)` (qui ne
    teste QUE 1071) vaut donc pour les deux : une cible portant deja 1071 n'en recoit aucun.

    Une fois les instances materialisees, `refresh_stat_modifier_effects` (mirror de
    `RefreshEffectsOperation`) tranche laquelle est ACTIVE et applique sa `ValueModification` --
    exactement comme le natif, qui cree l'entite-effet puis en delegue l'activite a sa
    `CreateActiveCondition`. No-op strict si l'unite n'est dans aucune aura, si elle n'a pas de
    stats, ou si son armure est nulle."""
    if state.effects is None:
        return None
    e = state.get_entity(int(unit_id))
    if e is None:
        return None
    # Gate `NOT HasEffect(target, 0x42f, 0, 6)` du selecteur CACHE, evalue UNE fois pour les deux
    # `AddEffect` (le natif ne teste que 1071 ; le test sur 1072 est un filet contre une pose
    # partielle d'un chemin offline).
    if state.effects.has_effect(int(unit_id), effect_type=CONTAGIONS_ARMOR_REDUCTION_1) or \
            state.effects.has_effect(int(unit_id), effect_type=CONTAGIONS_ARMOR_REDUCTION_2):
        return None
    carriers = aura_carriers(state, unit_id)
    if not carriers:
        # Aucune aura ne couvre l'unite -> `ContagionsOfNurgleAmount` = 0, hors des DEUX fenetres :
        # le natif materialiserait deux entites-effets INERTES, sans aucune modification de stat ni
        # evenement. Observable identique a « rien pose » -> on s'abstient (pas de bruit d'etat).
        return None
    sc = e.get_component(StatsComponent)
    if sc is None or sc.ctx is None:
        return None
    armor = int(sc.ctx.stat(StatType.FIXED_ARMOR) or 0)
    if armor <= 0:
        return None
    from ...effects import AddEffectOperation           # lazy : evite le cycle triggers <-> effects
    from ...refresh_effects import refresh_stat_modifier_effects
    posed = []
    for etype, name, key in _VARIANTS:
        pct = trait_var("ContagionsOfNurgle", key)
        if pct is None:
            continue
        # -X % du `FixedArmor` D'AVANT TOUTE POSE, materialise en DELTA PLAT. `pct` est NEGATIF au
        # gameconfig ; les deux instances lisent le MEME `armor` (capture avant la boucle).
        value = -round(armor * abs(int(pct)) / 100)
        # `source` = `owner@0x148` du natif = le PORTEUR de l'aura dont le trigger a fire, et c'est
        # LUI que `CreateActiveCondition` relit par `EffectSource(effect@0x150)` pour en tirer
        # l'equipe du compte. Plusieurs porteurs -> le premier de l'enumeration.
        # `active=False` = le chemin NATIF : `EffectComponent$$.ctor` laisse `IsActive @+0x5c`
        # zero-initialise, et c'est le premier `RefreshEffect` (juste apres la boucle) qui active
        # l'instance dont la fenetre contient le compte d'auras et applique SA modification. Sans
        # ce faux, `_apply_stat_mods` poserait les DEUX contributions EAGER (-20 % ET -40 %) sous
        # leur propre cle, hors de portee du driver -- exactement le cycle de vie qu'on porte ici.
        eff = AddEffectOperation.execute(state, source=int(carriers[0]), target=int(unit_id),
                                         effect_type=etype, name=name, value=value, active=False)
        if eff is not None:
            posed.append((name, value))
    if not posed:
        return None
    # `RefreshEffectsOperation` IMMEDIAT sur la cible : active l'instance dont la fenetre contient le
    # compte d'auras et applique SA `ValueModification` (`ApplyModification`) ; l'autre reste inerte.
    applied = refresh_stat_modifier_effects(state, int(unit_id))
    amount = contagions_of_nurgle_amount(state, int(unit_id), int(carriers[0]))
    active = [n for n, _v in posed if instance_is_active(state, int(unit_id), n)]
    active_name = active[0] if active else None
    return {"effect": active_name, "posed": [n for n, _v in posed], "unit": int(unit_id),
            "auras": (0 if amount is None else int(amount)), "armor_before": armor,
            "armor_delta": next((v for n, v in posed if n == active_name), 0),
            "carriers": carriers, "stat_mods": applied}
