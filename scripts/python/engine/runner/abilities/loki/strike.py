"""Abilities actives SINGLE-TARGET / SELF du namespace natif `Abilities.Active.Loki.*` :
ThunderousAssault (charge + stun + push), ArmoriumCherub (4x Flame + passif), SpiritLeech (attaque +
lifesteal Tyranids), ValkyrieStrike (airstrike differe). Cf. `loki/__init__.py`."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from fractions import Fraction

from ..base import ActiveAbility
from ...components import StatsComponent, PositionComponent
from ....entities.stats import StatType
from ....entities.effect_type import EffectType
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effects.magnitude import ability_var
from ....dsl.base import _round_fix64
from ....dsl.effects import ExecutionContext
from ....dsl.event_trigger_type import EventTriggerType   # #209 : EvaluateAbilities(EventTriggerType) node
from ....entities.behaviours import AtomicGroup, op_add, op_and
from ....entities.selectors import (Caster, Target, CasterTile, TargetTile, Union, UnitsFromFaction,
                                    AdjacentFriends, Alive, Cache, FixedTiles)
from ..behaviours import (AttackWithAttackDamage, AddEffect, EvaluateAbilities, PushUnit, MoveUnit,
                          KillDeadUnits, AddBondEffect, Heal, SetHealth, UseActiveAbility,
                          entities_from_state)

if TYPE_CHECKING:
    from ...state import State

STUNNED = int(EffectType.Stunned)                       # 1162 — effet COMPOSITE -> enfants 1165/1166/1167
PINNED = int(EffectType.Pinned)                         # 1065 — UI « Suppressed » — stat-mod Movement
VALKYRIE_STRIKE = int(EffectType.ValkyrieStrike_Effect)  # 1022 — airstrike DIFFÉRÉ, fire au tour suivant
BLACK_RAGE_EXTRA_MOVE = int(EffectType.BlackRage_ExtraMove)         # 1342 — self stat-mod +MOVEMENT
BLACK_RAGE_EXTRA_DAMAGE = int(EffectType.BlackRage_ExtraDamage)     # 1343 — self marqueur (+dmg-on-charge, résidu)
BLACK_RAGE_AUTOMATIC_UNIT = int(EffectType.BlackRage_AutomaticUnit)  # 1344 — self marqueur (act-again, résidu)


def thunderous_assault_tree(charge_dest: "TargetsSelector | None" = None) -> AtomicGroup:
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
            MoveUnit(Caster(), Cache(TargetTile())) ) )
    `charge_dest` = selecteur de tuile de la CHARGE ; defaut None -> un `Cache(TargetTile())` FRESH par cast.
    Ce `Cache` est le mirror 1:1 du `Cache(First(Nearest(Tiles(target),casterPos)))` natif PARTAGE entre
    l'attaque et la charge : il DOIT etre EVALUE (prime) PRE-push (le natif l'evalue a l'attaque, avant le
    push) -> `ThunderousAssaultAbility.execute_behaviour` construit et prime le cache avant `.execute()` puis
    l'injecte ici. Cf. #27 pour le pourquoi (sans memoisation, `TargetTile()` relu POST-push rend la tuile
    d'ATTERRISSAGE occupee, pas la tuile PRE-push liberee).
    `op_and` = `op_BitwiseAnd` (`CombinedBehaviour`) : effets PURS (flag@+0x20==0) -> TOUS les volets
    s'executent (l'attaque ne court-circuite pas le stun, meme si elle tue la cible — le stun s'applique
    inconditionnellement APRES, comme l'imperatif live-valide). `AtomicGroup` = inline (RE #201). Ordre natif =
    attaque -> stun -> push -> kill-dead -> move-caster (== `((((a&b)&c)&d)&e)` du decompile), meme `state.rng`
    (push/kill/move DETERMINISTES, aucun tirage rng -> n'alterent PAS l'ordre RNG : bit-exactness des degats
    preservee). `Target()` = `ctx.target` (cible du message) ; `Caster()` = +0x160.

    **slice-21a** : `PushUnit` -> `DisplaceUnitOperation` pousse la cible d'1 hex a l'oppose du caster (no-op
    si BigTarget/Immovable, cf. cible tyranTyrantGuard du test de stun). **slice-21b** : `KillDeadUnits(Caster,
    Target)` = `Kill(DownedUnits(target))` -- mort DEJA finalisee INLINE chez nous (damage.py:152) -> mirror
    structurel NO-OP (pas de double-fire on-death) ; `MoveUnit(Caster, Cache(TargetTile()))` = le CASTER CHARGE
    dans la tuile liberee par le push. Destination = `Cache(TargetTile())` MEMOISE PRE-push (== le
    `Cache(First(Nearest(Tiles(target),casterPos)))` natif, single-tile target -> collapse `TargetTile()`, meme
    collapse que l'attaque). ⚠ #27 : `ctx.target` est un `LiveUnit` (live-by-ref, pos re-lue a chaque acces,
    Voie A #6) -> `TargetTile()` NU relu POST-push rendrait la tuile d'ATTERRISSAGE (occupee), PAS la tuile
    PRE-push. Le `Cache` (prime a l'attaque cote natif ; prime dans `execute_behaviour` cote port) fige la tuile
    PRE-push : la charge vise la tuile liberee. La garde `CanAddUnit` (tuile libre) est LIVE dans la feuille
    `MoveUnit` (mirror `CanAddUnitFromAbility` sur contenu de tuile live) : le caster ne suit QUE si le push a
    reussi a liberer la tuile (sinon no-op)."""
    dest = charge_dest if charge_dest is not None else Cache(TargetTile())
    return AtomicGroup(op_and(op_and(op_and(op_and(
        AttackWithAttackDamage(Target(), "ThunderousAssault", "Power", is_melee=True),
        AddEffect(STUNNED, "Stunned", Target(), 1)),
        PushUnit(Caster(), Target())),
        KillDeadUnits(Caster(), Target())),
        MoveUnit(Caster(), dest)))


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
                                     damage_override=spirit_leech_get_attack_damage,  # GetAttackDamage (+extraDmg si Pinned)
                                     native_factory="ability")  # @181209a9f appelle @180de9dd0 -> AbilityDamageOperation
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
      & PushUnit(caster, target) & KillDeadUnits & MoveUnit(caster -> Cache(hex cible pre-push))  # slice-21a/b
    Le behaviour est l'arbre DSL COMPLET (`thunderous_assault_tree()`) : les feuilles émettent les MÊMES
    Operations que l'ancien impératif (`execute_ability_attack`/`AddEffectOperation`) → même mutation, même
    ordre, même `state.rng` (bit-exact BY CONSTRUCTION). Déplacement PORTÉ (slice-21a push + 21b charge) :
    le push pousse la cible d'1 hex (`DisplaceUnitOperation`), puis le caster CHARGE dans la tuile libérée —
    destination figée par un `Cache(TargetTile())` primé PRE-push (#27 : `ctx.target`=`LiveUnit` live-by-ref).
    VALIDÉ live : pose Stunned(1162, rem=1) + enfants 1165/1166/1167 sur la cible (cf. test_effect_stun_live)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ThunderousAssault)  # 1043

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # behaviour = arbre DSL (couche effet-nœuds, #203). Sans cible → tree no-op (Target()=None). Les
        # feuilles muent `state` via les Operations portées (skip dégât si rng non calé : replay effet-seul).
        if target_id is None:
            return {"attack": None, "dsl": True}
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        # #27 : `Cache(TargetTile())` = mirror du `Cache(First(Nearest(Tiles(target),casterPos)))` natif
        # PARTAGE attaque<->charge. Le natif le PRIME a l'attaque (pre-push) ; ici `ctx.target` est un `LiveUnit`
        # (pos live-by-ref, Voie A #6) -> on PRIME le cache MAINTENANT (pre-push) pour figer la tuile PRE-push de
        # la cible. Sans ce prime, la charge relirait `TargetTile()` POST-push (tuile d'atterrissage occupee) et
        # le caster ne chargerait jamais. On injecte le MEME cache dans l'arbre -> la feuille MoveUnit relit la
        # tuile PRE-push liberee par le push.
        charge_cache = Cache(TargetTile())
        charge_cache.evaluate(entities)                   # prime pre-push (1re eval == timing natif a l'attaque)
        thunderous_assault_tree(charge_dest=charge_cache).execute(entities, ectx)
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


def _black_rage_charge_positions(state, caster_id, target_id) -> list:
    """Collapse de `GetPossibleMovementTiles @1811ba5f0` = `TilesUnitCanMoveToChargeTarget(caster@0x160,
    target@0x178, UnitMovementRangeWithBonus(0x53e, ConfigConst 0xe))` PUIS `SortTilesByUtility(...,0x20)`
    -> `First(...,1)` (`ExecuteBehaviour @1811b9c20`). Sélecteur AI/pathfinding LOURD (kind S) -> COLLAPSE
    impératif (doctrine slice-18/19, véhicule `FixedTiles`) : tuiles ADJACENTES à la cible, ORDONNÉES par
    proximité au caster (charge la plus courte = mirror fidèle du choix de charge — au contact toute tuile
    adjacente donne la MÊME attaque mêlée). La feuille `MoveUnit` filtre libre+walkable (`CanAddUnit` live) et
    prend la 1re -> le caster charge au contact. La reachability (range de charge) est déjà garantie par la
    DÉCISION (`GetDynamicInvalidTargetReason @1811ba280`) au moment du cast. RÉSIDU documenté : l'ordre EXACT
    de `SortTilesByUtility` (métrique d'utilité par tuile) n'est pas reproduit -> la tuile de charge peut
    différer d'un hex adjacent équivalent (l'attaque connecte identiquement)."""
    import hexgeo
    board = getattr(state, "board", None)
    ce = state.get_entity(caster_id)
    te = state.get_entity(target_id)
    if board is None or ce is None or te is None:
        return []
    cpc = ce.get_component(PositionComponent)
    tpc = te.get_component(PositionComponent)
    if cpc is None or tpc is None:
        return []
    cpos = (cpc.col, cpc.row)
    ttid = board.id_at(tpc.col, tpc.row)
    if ttid is None:
        return []
    positions = []
    for tid in board.neighbours(ttid):
        t = board.by_id.get(tid)
        if t is not None:
            positions.append((t["col"], t["row"]))
    positions.sort(key=lambda p: hexgeo.distance(cpos, p))     # SortTilesByUtility -> First : charge la plus courte
    return positions


def black_rage_tree(charge_positions) -> "op_add":
    """Arbre de `BlackRageAbility.ExecuteBehaviour @1811b9c20` (id 1163, bloodDeathCompany « Lucien » —
    MIRROR du DÉCOMPILE) — TROIS phases (Execute / ExecuteAtomic / Execute) enchaînées :
        A. Execute( SetHealth(caster, hpPct% MaxHealth) )                       # GetSetHealthBehaviour @1811ba690
        B. ExecuteAtomic( AddEffect(1342 ExtraMove) & AddEffect(1343 ExtraDamage)
                          & AddEffect(1344 AutomaticUnit) )                     # 3 self-buffs, durée ZÉRO (remaining=0)
        C. Execute( MoveUnit(caster -> chargeTile) & UseActiveAbility(caster, target, NormalAttack) )

    Port : `op_add( op_add( SetHealth, AtomicGroup(buffs) ), op_and(MoveUnit, UseActiveAbility) )`. `SetHealth`
    = coût self (Lucien -> 30% MaxHealth). Les 3 `AddEffect` posent les self-buffs (`Caster()`, durée 0 =
    permanent, remaining=0 live) : ExtraMove applique +1 MOVEMENT (feuille -> effet `applied_stat_mods`),
    ExtraDamage/AutomaticUnit = marqueurs (résidus documentés côté classe d'effet). `MoveUnit(Caster(),
    FixedTiles(charge))` = la CHARGE (collapse de `SortTilesByUtility(TilesUnitCanMoveToChargeTarget)->First`),
    puis `UseActiveAbility(Caster(), Target())` = l'attaque NORMALE au contact (dispatch `AttackDamageOperation.
    execute` = attaque normale ECS, mêlée post-move). Ordre gauche->droite (Seq, effets PURS stop=False) =
    l'ordre natif setHealth -> buffs -> charge -> attaque (les buffs AVANT l'attaque : le natif l'exige pour
    le bonus ExtraDamage-on-charge). `AtomicGroup` = inline (RE #201, pass-through). NB : `AddStaticStatModifier
    Effect(1342)` natif est FOLDÉ dans `AddEffect(1342)` + la classe `BlackRageExtraMoveEffect` (qui DÉCLARE le
    stat-mod MOVEMENT) : même Operation `AddEffectOperation` en aval, même observable (statModSources)."""
    set_health = SetHealth(Caster(), "BlackRage", "hpPct")
    buffs = AtomicGroup(op_and(op_and(
        AddEffect(BLACK_RAGE_EXTRA_MOVE, "BlackRage_ExtraMove", Caster(), 0),        # durée 0 -> permanent (remaining=0)
        AddEffect(BLACK_RAGE_EXTRA_DAMAGE, "BlackRage_ExtraDamage", Caster(), 0)),
        AddEffect(BLACK_RAGE_AUTOMATIC_UNIT, "BlackRage_AutomaticUnit", Caster(), 0)))
    charge = op_and(MoveUnit(Caster(), FixedTiles(charge_positions)),
                    UseActiveAbility(Caster(), Target()))
    return op_add(op_add(set_health, buffs), charge)


class BlackRageAbility(ActiveAbility):
    """`BlackRageAbility.ExecuteBehaviour @1811b9c20` (id 1163, bloodDeathCompany « Lucien », #217) — MIRROR
    du DÉCOMPILE, arbre DSL 3 phases (`black_rage_tree`) :
        SetHealth(caster -> 30% MaxHealth)               # coût self (GetSetHealthBehaviour @1811ba690 ; hpPct=30)
      + [ AddEffect(1342 ExtraMove) & AddEffect(1343 ExtraDamage) & AddEffect(1344 AutomaticUnit) ]  # 3 self-buffs
      + [ MoveUnit(caster -> charge) & UseActiveAbility(caster, target, NormalAttack) ]              # charge + attaque

    Sélecteurs natifs : caster = `factory+0x160`, target = `factory+0x178` (l'ENNEMI chargé). Les effets +
    SetHealth ciblent le CASTER (self) ; l'attaque NORMALE frappe la cible AU CONTACT (après la charge).

    VALIDÉ live (31337, Lucien MaxHealth 15060 vs tyranTyrantGuard) : hp 9035 -> 4518 (=30% Max), pose 1342/
    1343/1344 (remaining=0), movement +1 (statModSources source-de-l'effet), charge tuile adjacente (5,8),
    attaque normale mêlée 4 coups. RÉSIDUS documentés : +extraDmg-on-charge (négligeable, gate IsCharging non
    porté), act-again AutomaticUnit (triggered PerformAIAction non porté). L'attaque normale offline consomme
    `state.rng` (dégât bit-exact seulement si rng calé ; la SÉQUENCE reste fidèle)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BlackRage)   # 1163
    ABILITY_ID = "BlackRage"

    def execute_behaviour(self, state, caster_id, target_id):
        if target_id is None:
            return None
        charge = _black_rage_charge_positions(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        black_rage_tree(charge).execute(entities_from_state(state, caster_id, target_id), ectx)
        set_hp = next((p for n, p in ectx.emitted if n == "SetHealth"), None)
        effects = [p.get("effect_type") for n, p in ectx.emitted if n == "AddEffect"]
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)
        attack = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        return {"ability": "BlackRage", "caster": caster_id, "target": target_id,
                "set_health": set_hp, "effects": effects, "moved": moved, "attack": attack, "dsl": True}
