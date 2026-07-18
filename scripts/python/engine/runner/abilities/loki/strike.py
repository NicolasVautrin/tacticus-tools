"""Abilities actives SINGLE-TARGET / SELF du namespace natif `Abilities.Active.Loki.*` :
ThunderousAssault (charge + stun + push), ArmoriumCherub (4x Flame + passif), SpiritLeech (attaque +
lifesteal Tyranids), ValkyrieStrike (airstrike differe). Cf. `loki/__init__.py`."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from fractions import Fraction

from ..base import ActiveAbility
from ...components import StatsComponent
from ....entities.stats import StatType
from ....entities.effect_type import EffectType
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effects.magnitude import ability_var
from ....dsl.base import _round_fix64
from ....dsl.effects import ExecutionContext
from ....dsl.event_trigger_type import EventTriggerType   # #209 : EvaluateAbilities(EventTriggerType) node
from ....entities.behaviours import AtomicGroup, op_add, op_and
from ....entities.selectors import (Caster, Target, CasterTile, TargetTile, Union, UnitsFromFaction,
                                    AdjacentFriends, Alive)
from ..behaviours import (AttackWithAttackDamage, AddEffect, EvaluateAbilities, PushUnit, MoveUnit,
                          KillDeadUnits, AddBondEffect, Heal, entities_from_state)

if TYPE_CHECKING:
    from ...state import State

STUNNED = int(EffectType.Stunned)                       # 1162 — effet COMPOSITE -> enfants 1165/1166/1167
PINNED = int(EffectType.Pinned)                         # 1065 — UI « Suppressed » — stat-mod Movement
VALKYRIE_STRIKE = int(EffectType.ValkyrieStrike_Effect)  # 1022 — airstrike DIFFÉRÉ, fire au tour suivant


def thunderous_assault_tree() -> AtomicGroup:
    """Arbre de `ThunderousAssaultAbility.ExecuteBehaviour @1812158b0` (id 1043, templSwordBrother — MIRROR
    du DECOMPILE) :
        ExecuteAtomic(
            AttackWithAttackDamage(caster, Units(Cache(First(Nearest(Tiles(target),casterPos)))),
                                   MinMaxDamage, profile=Power, hits=GetNumberConstant(0x2f))
          & AddEffect(0x48a Stunned, AbilityStateReference, target, TurnsFromRounds(1))
          & PushUnit(caster, target)
          & KillDeadUnits(caster, target, ForClearDeadUnitsBlockReviveOverkill)
          & MoveUnit(caster, CanAddUnit(Cache(First(Nearest(Tiles(target),casterPos)))), <options nuls>) )
    Port (arbre DEPLACEMENT COMPLET, slice-21b) :
        AtomicGroup( op_and( op_and( op_and( op_and(
            AttackWithAttackDamage(Target(),"ThunderousAssault","Power",melee),
            AddEffect(STUNNED,"Stunned",Target(),1) ),
            PushUnit(Caster(), Target()) ),
            KillDeadUnits(Caster(), Target()) ),
            MoveUnit(Caster(), TargetTile()) ) )
    `op_and` = `op_BitwiseAnd` (`CombinedBehaviour`) : effets PURS (flag@+0x20==0) -> TOUS les volets
    s'executent (l'attaque ne court-circuite pas le stun, meme si elle tue la cible — le stun s'applique
    inconditionnellement APRES, comme l'imperatif live-valide). `AtomicGroup` = inline (RE #201). Ordre natif =
    attaque -> stun -> push -> kill-dead -> move-caster (== `((((a&b)&c)&d)&e)` du decompile), meme `state.rng`
    (push/kill/move DETERMINISTES, aucun tirage rng -> n'alterent PAS l'ordre RNG : bit-exactness des degats
    preservee). `Target()` = `ctx.target` (cible du message) ; `Caster()` = +0x160.

    **slice-21a** : `PushUnit` -> `DisplaceUnitOperation` pousse la cible d'1 hex a l'oppose du caster (no-op
    si BigTarget/Immovable, cf. cible tyranTyrantGuard du test de stun). **slice-21b** : `KillDeadUnits(Caster,
    Target)` = `Kill(DownedUnits(target))` -- mort DEJA finalisee INLINE chez nous (damage.py:152) -> mirror
    structurel NO-OP (pas de double-fire on-death) ; `MoveUnit(Caster, TargetTile())` = le CASTER CHARGE dans la
    tuile liberee par le push. `TargetTile()` = tuile PRE-push de la cible : `ctx.target` etant un SNAPSHOT
    pre-cast (dict fige), `_pos(ctx.target)` reste la tuile d'origine meme apres le push -> collapse gratuit du
    `Cache(First(Nearest(Tiles(target),casterPos)))` natif (single-tile target ; meme collapse que l'attaque).
    La garde `CanAddUnit` (tuile libre) est LIVE dans la feuille `MoveUnit` (mirror `CanAddUnitFromAbility` sur
    contenu de tuile live) : le caster ne suit QUE si le push a reussi a liberer la tuile (sinon no-op)."""
    return AtomicGroup(op_and(op_and(op_and(op_and(
        AttackWithAttackDamage(Target(), "ThunderousAssault", "Power", is_melee=True),
        AddEffect(STUNNED, "Stunned", Target(), 1)),
        PushUnit(Caster(), Target())),
        KillDeadUnits(Caster(), Target())),
        MoveUnit(Caster(), TargetTile())))


def armorium_cherub_tree() -> AtomicGroup:
    """Arbre de `ArmoriumCherubAbility.ExecuteBehaviour @1811b4000` (id 1014, adeptRetributor «Vindicta» —
    MIRROR du DECOMPILE) :
        ExecuteAtomic(
            AttackWithAttackDamage(caster, target, MinMaxDamage(minDmg 0xc/maxDmg 0xd), profile=Flame,
                                   nrOfHits=GetNumberConstant(0x2f)=4)          # 4x Flame ranged, feu posé #136
          & EvaluateAbilities(0x4b=AttackInAtomicGroup) )                       # -> passif FireOfAbsolution
    Port : `AtomicGroup( op_and( AttackWithAttackDamage(Target(),"ArmoriumCherub","Flame",ranged),
                                 EvaluateAbilities(AttackInAtomicGroup, ranged=True) ) )`.
    `MinMaxDamage(target,0)` @180fb2dc0 = `RandomAmount(minDmg[0xc],maxDmg[0xd])` = le degat generique de la
    feuille `AttackWithAttackDamage` (bit-exact via `ability_attack_params` ; la branche `param_3!=0` =
    `Half(Sum(Direct,Direct))` = l'avg de PREDICTION #171, hors combat). `EvaluateAbilities(AttackInAtomicGroup)`
    = nœud DSL natif `EvaluateAbilitiesBehaviour @180fc48a0` qui EVALUE les passifs declenches du caster pour cet
    event (l'attaque d'ability atomique) -> `FireOfAbsolution` (splash 3x Flame + Maybe ignite ; passif porte
    `_fire_of_absolution_after_attack`, via `evaluate_abilities_for_event`). NB : NormalAttack passe `0x26`
    (event distinct, deja route par `after_hit_normal_attack`) ; les autres after-hit de l'attaque PRIMAIRE
    (feu, reset ActOfFaith) fire deja DANS l'Operation d'attaque -> pas de double-fire.
    `op_and` = `CombinedBehaviour` (PUR : les DEUX volets s'executent) ; `AtomicGroup` = inline (#201). Ordre =
    attaque PUIS passif (== l'ancien imperatif, meme `state.rng`) -> bit-exact BY CONSTRUCTION. ArmoriumCherub
    est range-2 -> `ranged=True` (== le littéral de l'imperatif ; FireOfAbsolution ne fire que sur ranged)."""
    return AtomicGroup(op_and(
        AttackWithAttackDamage(Target(), "ArmoriumCherub", "Flame", is_melee=False),
        EvaluateAbilities(int(EventTriggerType.AttackInAtomicGroup), ranged=True)))


def spirit_leech_get_attack_damage(state, caster_id, target_id, bmin, bmax):
    """`SpiritLeechAbility.GetAttackDamage @181209dd0` (COMBAT, param_3=0), MIRROR du DECOMPILE :
        ConditionalAmount( NOT HasEffect(target, Pinned 0x429), MinMaxDamage, MinMaxDamage + extraDmg )
    = si la cible est DEJA Pinned/« Suppressed » -> base + `extraDmg` (ConfigVar 8) ; sinon base seule.
    Le bonus est FLAT sur les 2 bornes AVANT le tirage per-coup. `extraDmg` est DANS
    `variablesAffectedByRarityBonus` -> multiplier = `AbilityVariablesMultiplierPercentage` du caster
    (contrairement a `hpToHealPct`, brut). Passe en `damage_override` a `AttackWithAttackDamage` (le natif
    passe cette node de degat a l'attaque). L'etat Pinned lu est celui d'AVANT le Pin de CE cast (l'attaque
    s'execute avant l'AddEffect Pinned dans l'arbre)."""
    eff = state.effects
    if eff is None or not eff.has_effect(target_id, effect_type=PINNED):
        return bmin, bmax
    ce = state.get_entity(caster_id)
    sc = ce.get_component(StatsComponent) if ce is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    extra = int(ability_var("SpiritLeech", "extraDmg", level, multiplier_pct=mult) or 0)
    return bmin + extra, bmax + extra


def spirit_leech_heal_amount(entities, ectx):
    """`SpiritLeechAbility.GetHealAmountForExecution @181209f00`, MIRROR du DECOMPILE :
        PercentageOf( LastAttackDamageMade(self), ConfigVar 0x4b = hpToHealPct )
    `LastAttackDamageMade` = total (degat SANTE) de la DERNIERE `AttackWithAttackDamage` emise (lu dans
    `ectx.emitted` = le seul volet d'attaque de SpiritLeech). `hpToHealPct` est HORS
    `variablesAffectedByRarityBonus` -> valeur brute par niveau (multiplier 100). `PercentageOf` natif passe
    `mode=1` = CEILING (`_round_fix64`, node canonique `entities/formulas.py`) : `ceil(total x pct/100)`
    (== `PercentageOf.Calculate`) — l'ancien imperatif tronquait (`int`), corrige ici au decompile."""
    total = 0
    for name, p in ectx.emitted:
        if name == "AttackWithAttackDamage":
            total = int(p.get("total") or 0)                # LastAttackDamageMade (derniere attaque du caster)
    if total <= 0:
        return 0
    caster = (entities.caster or {}).get("id")
    ce = ectx.state.get_entity(caster) if (ectx.state is not None and caster is not None) else None
    sc = ce.get_component(StatsComponent) if ce is not None else None
    level = getattr(sc.ctx, "active_ability_level", 0) if sc is not None else 0
    pct = int(ability_var("SpiritLeech", "hpToHealPct", level, multiplier_pct=100) or 0)
    return _round_fix64(Fraction(total * pct, 100), 1)      # PercentageOf(..., mode=1) = Ceiling (Fix64)


def spirit_leech_heal_targets() -> Union:
    """`SpiritLeechAbility.GetHealTargets @18120a1e0`, MIRROR du DECOMPILE :
        op_Addition( Self, UnitsFromFaction(Friends(self, AdjacentUnits(self,1)), 0xc=Tyranids) )
    = le CASTER (`Self`, SANS gate faction) UNION les allies VIVANTS de faction Tyranids adjacents (hex 1).
    Port : `Union(Caster(), UnitsFromFaction(Alive(AdjacentFriends(CasterTile())), "Tyranids"))`.
    `AdjacentFriends` (referent = caster) = `Friends(self, AdjacentUnits(self,1))` (allies du caster
    adjacents, self exclu via `_within` d>0) ; `Alive` mirror le filtre `Units`(=sur tuile, vivant) natif ;
    `UnitsFromFaction` filtre `FactionId=="Tyranids"` (0xc, `Enum.ToString(UnitFaction)`). `CasterTile` =
    tuile reelle du caster (runner : `caster_pos` None -> position courante = owner)."""
    return Union(Caster(),
                 UnitsFromFaction(Alive(AdjacentFriends(CasterTile())), "Tyranids"))


def spirit_leech_tree():
    """Arbre de `SpiritLeechAbility.ExecuteBehaviour @181209900` (id 1104, tyranNeurothrope — MIRROR du
    DECOMPILE) :
        Execute( op_Addition( op_Addition( op_Addition(
            AttackWithAttackDamage(self, target, GetAttackDamage, Psychic, nrOfHits=0x2f=1),   # [A] attaque
            SetCache(PercentageOf(LastAttackDamageMade, ConfigVar 0x4b hpToHealPct)) ),          # [heal amt]
            AddEffect(0x429 Pinned, target, DEFAUT) ),                                           # [Pin] cible
            Heal(self, GetHealTargets, cachedHealAmount) ) )                                     # [Heal] lifesteal
    Port (`Seq`/`op_add`) : Attack (degat = `GetAttackDamage` via `damage_override`) -> Pin -> Heal.
    Le noeud `SetCache` (memoisation du montant de heal) est FOLD dans `spirit_leech_heal_amount` (le `Heal`
    lit le total de la derniere attaque dans `ectx.emitted` = `LastAttackDamageMade`) : plumbing pur, sans
    effet observable dans l'executeur eager (meme reduction que `Cache`/#201/#202 — l'ordre A->Pin->Heal
    rend la MEME valeur : le Pin n'affecte pas le degat DEJA inflige, et le heal cible Self+allies pas la
    cible). PAS d'`AtomicGroup` (natif = `Execute`, PAS `ExecuteAtomic`). Aucun `KillDeadUnits`/`MoveUnit`
    dans ce natif. Bit-exact BY CONSTRUCTION (memes Operations/args/`state.rng` que l'imperatif).
    L'imperatif `SpiritLeechAbility.execute_behaviour` est REMPLACE par l'execution de cet arbre."""
    tgt = Target()
    attack = AttackWithAttackDamage(tgt, "SpiritLeech", "Psychic", is_melee=False,   # ranged (range 3), nrOfHits=0x2f=1
                                     damage_override=spirit_leech_get_attack_damage)  # GetAttackDamage (+extraDmg si Pinned)
    pin = AddEffect(PINNED, "Pinned", tgt, None)                                      # AddEffect(0x429), duree DEFAUT
    heal = Heal(spirit_leech_heal_targets(), spirit_leech_heal_amount)                # lifesteal (Self + Tyranids adj)
    return op_add(op_add(attack, pin), heal)                                          # ((A + Pin) + Heal)


def valkyrie_strike_tree() -> AddBondEffect:
    """Arbre de `ValkyrieStrikeAbility.ExecuteBehaviour @181229e40` (id 1018, astraSmnVoxcaster — MIRROR du
    DECOMPILE) :
        Execute( AddBondEffect(0x3fe ValkyrieStrike_Effect, AbilityStateReference, caster@0x160,
                               target@0x178, caster@0x160, dureeNode=ZERO, 0) )
    UN SEUL noeud (plain `Execute`, PAS `ExecuteAtomic`) : AUCUNE attaque immediate au cast. Le Blast
    (constants.damageProfile=Blast, nrOfHits=1) est le PAYLOAD de l'airstrike DIFFERE porte par l'effet 1022
    (frappe aerienne au tour suivant), HORS `ExecuteBehaviour`.
    Port : `AddBondEffect(VALKYRIE_STRIKE, "ValkyrieStrike_Effect", Caster(), Target(), None)`. `AddBondEffect`
    (== le natif, LIE source=caster <-> target : le caster capture la direction du bond, args 0x160 en 4e ET
    6e position) pose l'effet sur la cible, source=caster. Duree = `None` -> `DefaultAmountOfRounds` de l'effet
    1022 (mirror du duree-node ZERO natif = arg7 struct zero-initialise, PAS un `TurnsFromRounds(n)` explicite ;
    ScythingTalons/ThunderousAssault passaient un `TurnsFromRounds` — ValkyrieStrike ne l'a pas). L'`AbilityState
    Reference` (arg3) est FOLD dans source=caster (== CrushingClaws Taunt / les ports existants). Deterministe
    (aucun rng consomme) -> bit-exact BY CONSTRUCTION vs l'imperatif `AddEffectOperation.execute(source=caster,
    target, 1022)` (qui passait AUCUN duration_override). L'imperatif `ValkyrieStrikeAbility.execute_behaviour`
    est REMPLACE par cet arbre. NB : c'est aussi une CORRECTION de sur-tir (1018 a `constants.damageProfile` ->
    `_is_attack_ability`=True ; l'enregistrer ici `ported=True` EXCLUT 1018 du chemin generique qui tirerait un
    Blast IMMEDIAT a tort)."""
    return AddBondEffect(VALKYRIE_STRIKE, "ValkyrieStrike_Effect", Caster(), Target(), None)


class ThunderousAssaultAbility(ActiveAbility):
    """`ThunderousAssaultAbility.ExecuteBehaviour` @1812158b0 (id 1043, templSwordBrother).

    Séquence native (`&` = op_BitwiseAnd), MIGRÉE en ARBRE DSL (#203, `thunderous_assault_tree()`) :
        AttackWithAttackDamage(caster, Units(Cache(First(Nearest(Tiles(target),casterPos)))),
                               MinMaxDamage, profile=Power, hits=GetNumberConstant(0x2f))   # ← DSL
      & AddEffect(0x48a Stunned, source=casterStateRef, TurnsFromRounds(1))                 # ← DSL
      & PushUnit(target, 1 hex) & KillDeadUnits & MoveUnit(caster -> hex libéré)   # [déplacement — TODO]
    Le behaviour est l'arbre DSL (`AtomicGroup(op_and(AttackWithAttackDamage, AddEffect))`) : les feuilles
    émettent les MÊMES Operations que l'ancien impératif (`execute_ability_attack`/`AddEffectOperation`) →
    même mutation, même ordre, même `state.rng` (bit-exact BY CONSTRUCTION). push/kill/move = tranche
    déplacement différée (no-op, comme l'impératif). VALIDÉ live : pose Stunned(1162, rem=1) + enfants
    1165/1166/1167 sur la cible (cf. test_effect_stun_live)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ThunderousAssault)  # 1043

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # behaviour = arbre DSL (couche effet-nœuds, #203). Sans cible → tree no-op (Target()=None). Les
        # feuilles muent `state` via les Operations portées (skip dégât si rng non calé : replay effet-seul).
        if target_id is None:
            return {"attack": None, "dsl": True}
        ectx = ExecutionContext(state=state, rng=state.rng)
        thunderous_assault_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atk = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        return {"attack": atk, "dsl": True}


class ArmoriumCherubAbility(ActiveAbility):
    """`ArmoriumCherubAbility.ExecuteBehaviour @1811b4000` (id 1014, adeptRetributor «Vindicta»), MIGRÉ en
    ARBRE DSL (#209, `armorium_cherub_tree()`) :
        ExecuteAtomic(
            AttackWithAttackDamage(caster, target, MinMaxDamage(minDmg/maxDmg[level]), Flame,
                                   nrOfHits=GetNumberConstant(0x2f)=4)          # ← DSL (feuille AttackWithAttackDamage)
          & EvaluateAbilities(0x4b=AttackInAtomicGroup) )                       # ← DSL (nœud EvaluateAbilities)
    Actif RANGED (range 2). Profil Flame (`OnFire`) → POSE du feu sur la tuile-cible via le vecteur after-hit
    d'ability (`execute_ability_attack` → `_on_fire_damage_ability`, #136). i2 « Using Armorium Cherub does
    not end Vindicta's turn » = turn-flow (ne consomme pas le tour) — NON modélisé ici (concern turn-order).

    Le behaviour est l'arbre DSL : la feuille `AttackWithAttackDamage` émet la MÊME Operation que l'ancien
    impératif (`execute_ability_attack`, 4x Flame), et le nœud `EvaluateAbilities(AttackInAtomicGroup)` évalue
    le passif `FireOfAbsolution` (splash 3x Flame adjacents + 30% ignite/hex — `_fire_of_absolution_after_attack`
    via `evaluate_abilities_for_event`), EXACTEMENT comme l'appel inline de l'impératif → même mutation, même
    ordre (attaque PUIS passif), même `state.rng` = bit-exact BY CONSTRUCTION."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ArmoriumCherub)  # 1014
    ABILITY_ID = "ArmoriumCherub"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        armorium_cherub_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        main = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        passive = next((p["results"] for n, p in ectx.emitted if n == "EvaluateAbilities"), [])
        return {"ability": "ArmoriumCherub", "caster": caster_id, "target": target_id,
                "main_attack": main, "fire_of_absolution": passive, "dsl": True}


class SpiritLeechAbility(ActiveAbility):
    """`SpiritLeechAbility.ExecuteBehaviour @181209900` (id 1104, tyranNeurothrope — MIRROR du DECOMPILE) :
        Execute( op_Addition( op_Addition( op_Addition(
            AttackWithAttackDamage(self, target, GetAttackDamage, Psychic, nrOfHits=0x2f=1),   # attaque
            SetCache(PercentageOf(LastAttackDamageMade, ConfigVar 0x4b hpToHealPct)) ),          # montant heal
            AddEffect(0x429 Pinned, target, DEFAUT) ),                                           # « Suppressed » cible
            Heal(self, GetHealTargets, cachedHealAmount) ) )                                     # lifesteal

    `GetAttackDamage @181209dd0` COMBAT (param_3=0) = `ConditionalAmount(NOT HasEffect(target, Pinned),
    MinMaxDamage, MinMaxDamage + extraDmg)` : bonus a plat SI la cible est DEJA Pinned/Suppressed. Profil
    Psychic, ranged (range 3, nrOfHits=1). ⚠ COMBAT = CONFIG-based (config-avg×mult180 = 2593), != la
    PREDICTION Attack-based (~2670, slot 0x27) — DIVERGENCE NATIVE preview/combat (verdict #92).

    #149 slice-5 : `execute_behaviour` DELEGUE a `spirit_leech_tree()` (mirror 1:1 du decompile). Le degat
    conditionnel (`GetAttackDamage`) passe via `damage_override` ; le lifesteal (`GetHealTargets @18120a1e0`
    = Self + Tyranids adjacents ; `GetHealAmountForExecution @181209f00` = PercentageOf(LastAttackDamageMade,
    hpToHealPct, mode=1=Ceiling)) est porte par la feuille `Heal`. `SetCache`/`Cache` = fold (plumbing pur).
    Attaque + Pin bit-exact BY CONSTRUCTION vs l'ancien imperatif ; le montant heal est CORRIGE au decompile
    (Ceiling, l'imperatif tronquait — gap +0/+1 HP)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SpiritLeech)  # 1104
    ABILITY_ID = "SpiritLeech"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # bonus « Suppressed » = la cible est-elle DEJA Pinned AVANT le Pin de ce cast (== l'etat que lit
        # GetAttackDamage a l'attaque, qui precede l'AddEffect dans l'arbre) — capture pour le diag.
        suppressed = state.effects is not None and state.effects.has_effect(target_id, effect_type=PINNED)
        ectx = ExecutionContext(state=state, rng=state.rng)
        spirit_leech_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        main = None
        heal_amount = 0
        heals: list[dict] = []
        for name, p in ectx.emitted:
            if name == "AttackWithAttackDamage":
                main = p.get("attack")                            # LastAttackDamageMade (le seul volet d'attaque)
            elif name == "Heal":
                heal_amount = p.get("amount") or 0
                heals = p.get("heals") or []
        return {"ability": "SpiritLeech", "caster": caster_id, "target": target_id,
                "main_attack": main, "suppressed_bonus": suppressed,
                "heal_amount": heal_amount, "heals": heals, "dsl": True}


class ValkyrieStrikeAbility(ActiveAbility):
    """`ValkyrieStrikeAbility.ExecuteBehaviour` @181229e40 (id 1018, astraSmnVoxcaster), MIGRÉ en ARBRE DSL
    (#149 slice-9, `valkyrie_strike_tree()`) :
        Execute( AddBondEffect(0x3fe=1022 ValkyrieStrike_Effect, AbilityStateReference, caster↔target,
                               dureeNode=ZERO) )                                      # ← DSL (nœud unique)
    Séquence native = UNIQUEMENT `AddBondEffect(0x3fe=1022, caster↔target, durée ZÉRO → DefaultAmountOfRounds
    de l'effet 1022)` — AUCUNE attaque immédiate. Le Blast `minDmg/maxDmg` (constants.damageProfile=Blast,
    nrOfHits=1) est le PAYLOAD de l'airstrike DIFFÉRÉ : l'effet 1022 fire au tour suivant (frappe aérienne),
    PAS au cast.

    Le behaviour est l'arbre DSL (nœud unique `AddBondEffect`) : la feuille émet la MÊME Operation que
    l'ancien impératif (`AddEffectOperation.execute`, source=caster↔target, effet 1022, SANS duration_override
    = durée défaut) → même mutation, déterministe (aucun rng) = bit-exact BY CONSTRUCTION.

    ⚠ PORT DÉDIÉ = correction d'un SUR-TIR. 1018 a `constants.damageProfile` → `_is_attack_ability` renvoie
    True → le chemin GÉNÉRIQUE de `summon_ai._apply_active_ability` TIRERAIT à tort un Blast IMMÉDIAT. En
    l'enregistrant ici (handler `ported=True`), on EXCLUT 1018 du générique : le cast ne fait QUE poser
    l'effet différé (fidèle). L'airstrike différé lui-même (fire du 1022 → dégât) = sa propre tranche
    pending-effect (TODO)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ValkyrieStrike)  # 1018
    ABILITY_ID = "ValkyrieStrike"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        valkyrie_strike_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        bond = next((p for n, p in ectx.emitted if n == "AddBondEffect"), None)
        return {"ability": "ValkyrieStrike", "caster": caster_id, "target": target_id,
                "deferred_effect": (bond or {}).get("effect_type", VALKYRIE_STRIKE),
                "immediate_attack": None, "dsl": True}
