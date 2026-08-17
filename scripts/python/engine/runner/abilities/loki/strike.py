"""Abilities actives SINGLE-TARGET / SELF du namespace natif `Abilities.Active.Loki.*` :
ThunderousAssault (charge + stun + push), ArmoriumCherub (4x Flame + passif), SpiritLeech (attaque +
lifesteal Tyranids), ValkyrieStrike (airstrike differe). Cf. `loki/__init__.py`."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from fractions import Fraction

from ..base import ActiveAbility
from ..targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE,
                         RANGED_BOOL_TRUE, TargetingOptions)
from ..targeting_rule import TargetingRule as TR
from ...components import StatsComponent
from ....entities.stats import StatType
from ....entities.effect_type import EffectType
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effects.magnitude import ability_var
from ....dsl.base import Const, _round_fix64
from ....dsl.effects import ExecutionContext
from ....dsl.event_trigger_type import EventTriggerType   # #209 : EvaluateAbilities(EventTriggerType) node
from ....entities.behaviours import AtomicGroup, op_add, op_and
from ....entities.selectors.accessors import CasterTile, FixedTiles, SelectTile, Target, TargetTile
from ....entities.selectors.geometry import Cache
from ....entities.selectors.tiles import Caster, tiles_unit_can_move_to_charge_target
from ....entities.selectors.units import AdjacentFriends, Alive, Union, UnitsFromFaction
from ....utilities.tile import first_tile_by_utility
from ....utilities.utility_type import UtilityType
from ..behaviours.combat import AttackWithAttackDamage, EvaluateAbilities, UseActiveAbility
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddBondEffect, AddEffect
from ..behaviours.lifecycle import KillDeadUnits
from ..behaviours.movement import MoveUnit, PushUnit
from ..behaviours.stats import Heal, SetHealth
from ....entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve
#: #585-r1, build `rnca9r7q6c`, littéral par littéral (JAMAIS par symetrie : deux call-sites
#: du releve passent `Any` parce que leur source est un ensemble de MORTS).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


if TYPE_CHECKING:
    from ...state import State

STUNNED = int(EffectType.Stunned)                       # 1162 — effet COMPOSITE -> enfants 1165/1166/1167
PINNED = int(EffectType.Pinned)                         # 1065 — UI « Suppressed » — stat-mod Movement
VALKYRIE_STRIKE = int(EffectType.ValkyrieStrike_Effect)  # 1022 — airstrike DIFFÉRÉ, fire au tour suivant
BLACK_RAGE_EXTRA_MOVE = int(EffectType.BlackRage_ExtraMove)         # 1342 — self stat-mod +MOVEMENT
BLACK_RAGE_EXTRA_DAMAGE = int(EffectType.BlackRage_ExtraDamage)     # 1343 — self marqueur (+dmg-on-charge, résidu)
BLACK_RAGE_AUTOMATIC_UNIT = int(EffectType.BlackRage_AutomaticUnit)  # 1344 — self marqueur (act-again, résidu)
CORD_CLAW_ADDITIONAL_HITS = int(EffectType.CordClaw_AdditionHits)   # 1250 (0x4e2) — self-buff coups additionnels (#179)


def thunderous_assault_tree(charge_dest: "TargetsSelector | None" = None) -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$ExecuteBehaviour` (id 1043, templSwordBrother — MIRROR
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
    # `SelectTile` = mirror `TargetsSelector$$SelectTile` : la destination de `MoveUnit` est UNE tuile,
    # et le natif collapse ici `First(Nearest(Tiles(target), casterPos))` -- une main tile (#459).
    dest = charge_dest if charge_dest is not None else Cache(SelectTile(TargetTile()))
    return AtomicGroup(op_and(op_and(op_and(op_and(
        AttackWithAttackDamage(Target(), "ThunderousAssault", "Power", is_melee=True),
        AddEffect(STUNNED, "Stunned", Target(), duration_rounds=1)),   # TurnsFromRounds(1) IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$ExecuteBehaviour -> converti (#98)
        PushUnit(Caster(), Target())),
        KillDeadUnits(Caster(), Target())),
        MoveUnit(Caster(), dest)))


def armorium_cherub_tree() -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$ExecuteBehaviour` (id 1014, adeptRetributor «Vindicta» —
    MIRROR du DECOMPILE) :
        ExecuteAtomic(
            AttackWithAttackDamage(caster, target, MinMaxDamage(minDmg 0xc/maxDmg 0xd), profile=Flame,
                                   nrOfHits=GetNumberConstant(0x2f)=4)          # 4x Flame ranged, feu posé #136
          & EvaluateAbilities(0x4a=AttackInAtomicGroup) )                       # -> passif FireOfAbsolution
    Port : `AtomicGroup( op_and( AttackWithAttackDamage(Target(),"ArmoriumCherub","Flame",ranged),
                                 EvaluateAbilities(AttackInAtomicGroup, ranged=True) ) )`.
    `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(target,0) = `RandomAmount(minDmg[0xc],maxDmg[0xd])` = le degat generique de la
    feuille `AttackWithAttackDamage` (bit-exact via `ability_attack_params` ; la branche `param_3!=0` =
    `Half(Sum(Direct,Direct))` = l'avg de PREDICTION #171, hors combat). `EvaluateAbilities(AttackInAtomicGroup)`
    = nœud DSL natif `EvaluateAbilitiesBehaviour IdunBattle.Entities.Behaviours.EvaluateAbilitiesBehaviour$$Execute` qui EVALUE les passifs declenches du caster pour cet
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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetAttackDamage` (COMBAT, param_3=0), MIRROR du DECOMPILE :
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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealAmountForExecution`, MIRROR du DECOMPILE :
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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealTargets`, MIRROR du DECOMPILE :
        op_Addition( Self, UnitsFromFaction(Friends(self, AdjacentUnits(self,1)), 0xc=Tyranids) )
    = le CASTER (`Self`, SANS gate faction) UNION les allies VIVANTS de faction Tyranids adjacents (hex 1).
    Port : `Union(Caster(), UnitsFromFaction(Alive(AdjacentFriends(CasterTile())), "Tyranids"))`.
    `AdjacentFriends` (referent = caster) = `Friends(self, AdjacentUnits(self,1))` (allies du caster
    adjacents, self exclu via `_within` d>0) ; `Alive` mirror le filtre `Units`(=sur tuile, vivant) natif ;
    `UnitsFromFaction` filtre `FactionId=="Tyranids"` (0xc, `Enum.ToString(UnitFaction)`). `CasterTile` =
    tuile reelle du caster (runner : `caster_pos` None -> position courante = owner)."""
    # #585-r1 : `AdjacentUnits(gs, gs@0x50, unique: 1, 3)`, `Friends(gs, gs@0x48, ., 3)` et
    # `UnitsFromFaction(gs, ., ToString(UnitFaction 0xc) = "Tyranids", 3)` -- littéraux LUS dans
    # `...SpiritLeechAbility$$GetHealTargets`. Le port collapse les deux premiers en
    # `AdjacentFriends` ; le predicat etant PUR, un seul passage suffit.
    return Union(Caster(),
                 UnitsFromFaction(Alive(AdjacentFriends(CasterTile(), selection_type=SELECTION)),
                                  "Tyranids", selection_type=SELECTION))


def spirit_leech_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$ExecuteBehaviour` (id 1104, tyranNeurothrope — MIRROR du
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
                                     native_factory="ability")  # IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$ExecuteBehaviour+0x19f appelle IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage -> AbilityDamageOperation
    pin = AddEffect(PINNED, "Pinned", tgt, None)                                      # AddEffect(0x429), duree DEFAUT
    heal = Heal(spirit_leech_heal_targets(), spirit_leech_heal_amount)                # lifesteal (Self + Tyranids adj)
    return op_add(op_add(attack, pin), heal)                                          # ((A + Pin) + Heal)


def valkyrie_strike_tree() -> AddBondEffect:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ValkyrieStrikeAbility$$ExecuteBehaviour` (id 1018, astraSmnVoxcaster — MIRROR du
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


def _seed_cord_claw_hits_level(state: "State", caster_id: int) -> None:
    """Seede `ability_level`/`ability_variables_multiplier` sur l'effet `CordClaw_AdditionHits` (0x4e2)
    FRAICHEMENT pose (self-buff) depuis le ctx du CASTER (source). Le natif capture une `AbilityStateReference`
    dans l'effet, indexant ses vars per-niveau (`GetMinMaxDamage2` = `ConfigVar(minDmg_2/maxDmg_2,
    AbilityStateFromEffect)` = niveau de CordClaw sur l'owner) ; `AddEffectOperation` ne propage PAS ces champs
    (level=None -> `CordClawAdditionalHitsEffect.additional_hit_groups` resoudrait minDmg_2/maxDmg_2 au NIVEAU 1,
    idx 0 de `ability_var`). CordClaw etant l'ability ACTIVE du caster, le niveau = `active_ability_level`
    (fallback `passive_ability_level` -- ce que le seeding LIVE utilise, snapshot.py:160). Local (pas dans
    `AddEffectOperation`, qui doit rester agnostique) -- precedent EXACT : `imperative.py._seed_active_ability_level`
    (DoctrinaImperatives) + `genestealer.py` owner-effects poses par trigger."""
    if state.effects is None:
        return
    ce = state.get_entity(caster_id)
    csc = ce.get_component(StatsComponent) if ce is not None else None
    cctx = csc.ctx if csc is not None else None
    lvl = getattr(cctx, "active_ability_level", None)
    if lvl is None:
        lvl = getattr(cctx, "passive_ability_level", None)
    mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
    for e in state.effects.by_unit.get(int(caster_id), []):
        if (not e.consumed) and e.effect_type == CORD_CLAW_ADDITIONAL_HITS:
            e.ability_level = lvl
            e.ability_variables_multiplier = mult


def cord_claw_tree() -> "op_add":
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.CordClawAbility$$ExecuteBehaviour` (id 1122, admecRuststalker « Exitor-Rho » —
    MIRROR du DECOMPILE) :
        Execute( op_Addition(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                                   GetDamageProfile=DirectDamage, nrOfHits=GetHits=GetNumberConstant(0x2f)=4),  # attaque
            AddEffect(0x4e2=1250 CordClaw_AdditionHits, source=AbilityStateReference, target=Self@0x148,
                      TurnsFromRounds(2)) ) )                                                                   # self-buff
    Port : `op_add( AttackWithAttackDamage(Target(),"CordClaw","DirectDamage",melee), AddEffect(0x4e2,
    "CordClaw_AdditionHits", Caster(), 2) )` -- plain `Execute` (PAS `ExecuteAtomic`, contraste CrushingClaws/
    ArmoriumCherub ; == SpiritLeech).

    JUMEAU STRUCTUREL d'ArmoriumCherub (attaque MinMax + noeud unique) mais le 2e volet est un `AddEffect`
    self-buff (au lieu d'`EvaluateAbilities`). Details RE :
    - `GetHits` : le decompile appelle litteralement `ArmoriumCherubAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` = MISLABEL
      GSHARED (corps de methode DEDUPLIQUE : `GetNumberConstant(config@0x60, 0x2f)`). Appele avec `param_1`=
      l'instance CordClaw -> lit la config CORDCLAW (`nrOfHits`=4), PAS celle d'ArmoriumCherub. La feuille
      `AttackWithAttackDamage` lit `nrOfHits` (0x2f, hits_key defaut) via `ability_attack_params("CordClaw")`.
    - profil `GetDamageProfile` = `DirectDamage` (constants.damageProfile ; PiercingRatio 100 = ignore armure,
      i2 « Direct Damage »). Attaque MELEE (attackRangeType=Melee).
    - cible de l'`AddEffect` = `Self@0x148` (noeud sélecteur d'une CLASSE DISTINCTE de `Caster@0x160`, cf.
      `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` -- 0x148 sert de référentiel « owner » dans
      `HasUsedActiveAbilityThisTurnTrigger`). Pour un cast SELF, `Self` == le caster (Exitor-Rho) -> porté via
      `Caster()` (observable identique : l'effet se pose sur le caster, i2 « All of Exitor-Rho's further
      attacks »). BlackRage pose ses self-buffs via `Caster@0x160` ; le nuance Self/Caster n'a AUCUN effet
      observable ici (self-cast).
    - `AddEffect` source = `AbilityStateReference` (= le caster) ; la feuille l'assigne implicitement
      (`entities.caster`). Durée `TurnsFromRounds(2)` (i2 « until the end of his next turn »).

    L'ordre `op_Addition` (== `op_add`, Seq gauche->droite, effets PURS) = attaque PUIS pose de l'effet : le
    self-buff N'EST PAS present pendant l'attaque du cast (le canal #179 lu par `_collect_additional_hit_groups`
    a l'attaque ne le voit pas encore) -> le cast frappe 4x DirectDamage SANS coups additionnels ; les coups
    additionnels (+nrOfHits_2=2 [minDmg_2,maxDmg_2] DirectDamage, effet DEJA porté `hits.py:CordClawAdditional
    HitsEffect`) s'appliquent aux attaques SUIVANTES (tour N+1). Aucun tirage RNG dans l'`AddEffect` -> l'ordre
    n'altere PAS l'ordre RNG de l'attaque : bit-exact BY CONSTRUCTION vs un imperatif attaque->pose."""
    attack = AttackWithAttackDamage(Target(), "CordClaw", "DirectDamage", is_melee=True)   # 4x DirectDamage melee
    # `TurnsFromRounds(2)` natif (IdunBattleLogic.Entities.Abilities.Active.Loki.CordClawAbility$$ExecuteBehaviour) -> `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns(2) (#98)
    self_buff = AddEffect(CORD_CLAW_ADDITIONAL_HITS, "CordClaw_AdditionHits", Caster(), duration_rounds=2)
    return op_add(attack, self_buff)


class ThunderousAssaultAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$ExecuteBehaviour (id 1043, templSwordBrother).

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

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET + FLAGS** (la 2e des trois
    # formes, celle ou le litteral visible n'est PAS le masque effectif).
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$.ctor` recopie les
    # 0x40 octets du preset STATIQUE de `TargetingOptions` (offset RELATIF +0x40 du bloc
    # `<class>+0xb8`), puis :
    #     TargetingOptions..ctor(&opts, &preset, 0x10000000, 0)   # surcharge (dst, preset, flags)
    #     AActiveAbility..ctor(this, &opts, 0, 0)                 # 3e arg = 0 = DirectTargetAttack
    # La surcharge (dst, preset, flags) recopie le preset champ par champ SAUF `Rules`, qu'elle
    # COMBINE : `dst+0x28 = flags | preset+0x28`. Le masque EFFECTIF est donc
    # `0x10000000 | *(statics+0x68)`, et `*(statics+0x68)` est la constante ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` = **0x4000** -> **0x10004000**.
    # Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`) -- 0x10004000 est la somme
    # de ces deux bits, il ne reste AUCUN bit residuel :
    #     0x4000      (bit 14) TargetIsEnemy   -> PORTE (refus sur soi-meme / un allie ;
    #                                             `TargetingQuery$$UnitsCanAttackEachOther`).
    #     0x10000000  (bit 28) CasterCanMove   -> regle du volet CASTER, PAS du volet cible :
    #                 `TargetingQuery$$GetInvalidCasterReason` fait
    #                 `if ((rules & 0x10000000) && !UnitExtensions.CanMove(caster))
    #                      return GenericBrokenTargetingRule(0x10000000);`
    #                 (immediatement apres la clause `CasterHasNotMoved`). NON PORTEE -- cf.
    #                 `get_invalid_caster_reason`, dont la liste « NON PORTEES » la cite deja :
    #                 `IdunBattle.Entities.UnitExtensions$$CanMove` = `!HasTrait(0x418 Stationary)
    #                 && MovementComponent.IsAllowedToMove(unit)`, et ce second volet est
    #                 `movementBlockers.Count == 0` sur un dictionnaire (`MovementComponent+0x50`)
    #                 que le port ne modelise PAS (son seul poseur du build est
    #                 `IdunBattle.Entities.Effects.Loki.InstinctiveBehaviourBlockMovementEffect`).
    #                 Porter le seul volet `Stationary` serait un demi-mirror INVALIDABLE : aucun
    #                 porteur de 1043 ne peut recevoir ce trait (son unique poseur est
    #                 `DutyEternalAbility` -> `AddTrait(ActiveTarget, 0x418)` sur le dreadnought
    #                 invoque, qui n'a pas ThunderousAssault). Residu documente, pas de port
    #                 speculatif. Mesure : AUCUNE autre ability du registre ne porte le bit 28.
    # PORTEE : le MEME preset `+0x40` porte `TargetingRange` <- `TargetingRange` statique `+0x30`
    # (`IdunBattle.Core.Services.TargetingRange$$.cctor` : `+0x30` onlyAdjacent = `RangedBool.True`,
    # `+0x38` overrideRange = `Nullable(1)`, `+0x40` overrideRangeFunc = null) = `RANGE_ADJACENT` ;
    # et `forceMeleeTarget` (`<preset>+0x20`) = 1 = `RangedBool.False` (aucun clamp melee a poser --
    # la portee est DEJA l'adjacence). `onlyAdjacent` fait prendre au filtre statique la branche
    # `battleQuery.AreEntitiesAdjacent(casterTiles, target)` : la CHARGE de ThunderousAssault ne se
    # declenche que sur une cible DEJA au contact -- le deplacement de l'arbre (`PushUnit` puis
    # `MoveUnit(caster, Cache(TargetTile()))`) est un pas d'UN hex, pas une charge a distance.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy | TR.CasterCanMove,
                                         self_cast=False, range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

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
        charge_cache = Cache(SelectTile(TargetTile()))    # UNE tuile (`SelectTile`, #459)
        charge_cache.evaluate(entities)                   # prime pre-push (1re eval == timing natif a l'attaque)
        thunderous_assault_tree(charge_dest=charge_cache).execute(entities, ectx)
        atk = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        return {"attack": atk, "dsl": True}


class ArmoriumCherubAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$ExecuteBehaviour` (id 1014, adeptRetributor «Vindicta»), MIGRÉ en
    ARBRE DSL (#209, `armorium_cherub_tree()`) :
        ExecuteAtomic(
            AttackWithAttackDamage(caster, target, MinMaxDamage(minDmg/maxDmg[level]), Flame,
                                   nrOfHits=GetNumberConstant(0x2f)=4)          # ← DSL (feuille AttackWithAttackDamage)
          & EvaluateAbilities(0x4a=AttackInAtomicGroup) )                       # ← DSL (nœud EvaluateAbilities)
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

    # GATE DE CIBLE (#115) + PORTEE (#241) — forme de ctor = **PRESET STATIQUE COPIE** (aucun appel a
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`, donc AUCUN litteral de masque n'est visible
    # dans le ctor de l'ability). `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$.ctor`
    # recopie les 0x40 octets du champ STATIQUE de `TargetingOptions` a l'offset +0x140 du bloc
    # `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 0, 0)      # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Le masque EFFECTIF est donc la constante ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`, soit `*(statics+0x168)`
    # = **0x4002**. Ce n'est PAS la surcharge « preset + flags » (`TargetingOptions..ctor(&opts,
    # &preset, <flags>, 0)`, qui ferait `Rules <- preset.Rules | flags`) : la copie est integrale,
    # il n'y a aucun flag a OR-er.
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`, noms VERBATIM du mirror genere) :
    #     0x2     TargetMatchesDynamicRule  -> consulte `GetDynamicInvalidTargetReason` ; la classe
    #                                          n'en fournit AUCUN corps propre (ses seuls corps sont
    #                                          `...ArmoriumCherubAbility$$.ctor`,
    #                                          `...$$ExecuteBehaviour` et le `...$$GetHits` gshared)
    #                                          -> defaut `AActiveAbility` = 0 = aucun refus.
    #     0x4000  TargetIsEnemy             -> PORTE (refus sur soi-meme / un allie).
    # PORTEE : le meme preset `+0x140` porte `TargetingRange` <- `TargetingRange` statique `+0x18`
    # (`useRangeFromConfig`) -> `SetConfigValuesInTargetingOptions` pose `OverrideRange` =
    # `GetNumberConstant(0x16 range)` = `ArmoriumCherub.constants.range` = **2** ; et
    # `forceMeleeTarget` (`<preset>+0x20`) = 0 = `RangedBool.True` -> clamp a 1 + `onlyAdjacent`
    # quand `ShouldApplyRangedInMelee` (un ennemi vivant, ciblable et non-Steppable est au contact
    # de Vindicta). MEME preset que Executioner / HarvesterOfSouls / PlasmaCannon.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$ExecuteBehaviour` (id 1104, tyranNeurothrope — MIRROR du DECOMPILE) :
        Execute( op_Addition( op_Addition( op_Addition(
            AttackWithAttackDamage(self, target, GetAttackDamage, Psychic, nrOfHits=0x2f=1),   # attaque
            SetCache(PercentageOf(LastAttackDamageMade, ConfigVar 0x4b hpToHealPct)) ),          # montant heal
            AddEffect(0x429 Pinned, target, DEFAUT) ),                                           # « Suppressed » cible
            Heal(self, GetHealTargets, cachedHealAmount) ) )                                     # lifesteal

    `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetAttackDamage` COMBAT (param_3=0) = `ConditionalAmount(NOT HasEffect(target, Pinned),
    MinMaxDamage, MinMaxDamage + extraDmg)` : bonus a plat SI la cible est DEJA Pinned/Suppressed. Profil
    Psychic, ranged (range 3, nrOfHits=1). ⚠ COMBAT = CONFIG-based (config-avg×mult180 = 2593), != la
    PREDICTION Attack-based (~2670, slot 0x27) — DIVERGENCE NATIVE preview/combat (verdict #92).

    #149 slice-5 : `execute_behaviour` DELEGUE a `spirit_leech_tree()` (mirror 1:1 du decompile). Le degat
    conditionnel (`GetAttackDamage`) passe via `damage_override` ; le lifesteal (`IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealTargets`
    = Self + Tyranids adjacents ; `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealAmountForExecution` = PercentageOf(LastAttackDamageMade,
    hpToHealPct, mode=1=Ceiling)) est porte par la feuille `Heal`. `SetCache`/`Cache` = fold (plumbing pur).
    Attaque + Pin bit-exact BY CONSTRUCTION vs l'ancien imperatif ; le montant heal est CORRIGE au decompile
    (Ceiling, l'imperatif tronquait — gap +0/+1 HP)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SpiritLeech)  # 1104
    ABILITY_ID = "SpiritLeech"

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE** (la 3e des
    # trois formes) : `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$.ctor`
    # n'appelle AUCUN `IdunBattle.Core.Services.TargetingOptions$$.ctor` -- il recopie les 0x40
    # octets du champ STATIQUE de `TargetingOptions` a l'offset RELATIF **+0x180** du bloc
    # `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 0, 0)   # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Aucun litteral de masque n'est donc visible dans le ctor : le masque EFFECTIF est la constante
    # ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`, soit
    # `*(statics+0x1a8)` = **0x4002**. Ce n'est PAS la surcharge « preset + flags » (qui ferait
    # `Rules <- preset.Rules | flags`) : la copie est integrale, il n'y a aucun flag a OR-er.
    # Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`, noms VERBATIM du mirror
    # genere) -- 0x2 + 0x4000 = 0x4002, il ne reste AUCUN bit residuel :
    #     0x2     (bit 1)  TargetMatchesDynamicRule  -> point d'extension : le filtre statique
    #                      invoque la regle-delegue `options+0x38` (slot vtable +0x480). La classe
    #                      native ne fournit AUCUN corps `SpiritLeechAbility$$GetDynamicInvalid
    #                      TargetReason` (ses seuls corps sont `$$.ctor`, `$$ExecuteBehaviour`,
    #                      `$$GetAttackDamage`, `$$GetHealTargets`, `$$GetHealAmountForExecution`,
    #                      `$$GetHealAmountForPrediction`, `$$GetHealAmountFromDamageAmount`,
    #                      `$$GetSuppressCondition`) -> defaut `AActiveAbility` = 0 = aucun refus.
    #                      Cote port : `ActiveAbility.get_dynamic_invalid_target_reason` (defaut 0).
    #     0x4000  (bit 14) TargetIsEnemy             -> PORTE (`TargetingQuery$$UnitsCanAttackEach
    #                      Other`) : refus sur soi-meme et sur un allie.
    # PORTEE : le MEME preset `+0x180` porte `TargetingRange` <- `TargetingRange` statique **+0x18**
    # (`IdunBattle.Core.Services.TargetingRange$$.cctor` : `onlyAdjacent = RangedBool.False`,
    # `useRangeFromConfig = true`, `useWholeBoard = false`, `overrideRange` vide) = `RANGE_FROM_CONFIG`
    # -> `AActiveAbility$$SetConfigValuesInTargetingOptions` pose `OverrideRange =
    # GetNumberConstant(0x16 range)` = `SpiritLeech.constants.range` = **3**.
    # `forceMeleeTarget` (`<preset>+0x20` = `*(statics+0x1a0)`) = **1** = `RangedBool.False` -> AUCUN
    # clamp melee (`GetRange` n'entre pas dans la branche `ShouldApplyRangedInMelee`).
    # ATTENTION -- LA VOISINE MENT : `ArmoriumCherub` (1014) est dans CE fichier, de la MEME forme,
    # avec le MEME masque 0x4002 et le MEME `RANGE_FROM_CONFIG`... mais son preset est `+0x140` et y
    # ecrit `forceMeleeTarget = 0 = RangedBool.True` (`*(statics+0x160)`). Les deux presets ne
    # different QUE par ce champ, et il change le regime de portee au contact : Vindicta clampe a 1,
    # le Neurothrope garde ses 3 hexes. Copier le preset du voisin aurait produit un gate FAUX.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         self_cast=False, range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_FALSE)

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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ValkyrieStrikeAbility$$ExecuteBehaviour (id 1018, astraSmnVoxcaster), MIGRÉ en ARBRE DSL
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

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ValkyrieStrikeAbility$$.ctor` — ctor de la
    # TROISIEME FORME : il n'appelle AUCUN `TargetingOptions$$.ctor`. Il recopie les 0x40 octets du
    # PRESET statique `TargetingOptions` (bloc de statiques de la classe, offset RELATIF +0x1c0) puis
    # les passe tels quels a `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, &opts, 2)` --
    # le litteral `2` etant l'`AbilityAttackType.Others` deja transcrit dans `ABILITY_ATTACK_TYPE`.
    # Le contenu du preset est ecrit par `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     <preset>+0x00 isSelfCasting    = 0
    #     <preset>+0x08 range            = `TargetingRange` statics+0x48 = UseWholeBoard
    #                                      (`IdunBattle.Core.Services.TargetingRange$$.cctor` :
    #                                       +0x48 onlyAdjacent=RangedBool.False, +0x4d useWholeBoard=1)
    #     <preset>+0x20 forceMeleeTarget = 1 = RangedBool.False
    #     <preset>+0x28 rules            = 0x6000040
    #     <preset>+0x30/+0x38 delegues   = 0 (aucune regle dynamique)
    # 0x6000040 = TargetIsTile (0x40) | AllowObscuredTargetByElevation (bit 25)
    #                                 | AllowObscuredTargetByWalls (bit 26) -- lecture EXHAUSTIVE, il
    # ne reste aucun bit non nomme. Semantique : frappe AERIENNE sur une TUILE (domaine TILE, cf.
    # `TargetingOptions$$get_IsTileTargeting`), et les deux `AllowObscured*` levent la ligne de vue --
    # un airstrike ne se soucie ni des murs ni de l'elevation. AUCUNE regle de CAMP (`TargetIsFriendly`
    # / `TargetIsCaster` absents) -> `refuses_all_enemy_targets` = False : le routage IA est inchange.
    # Le SEUL gate qui mord offline est la branche `TargetIsTile` (tuile-cible non marchable ->
    # `ValidRequest`) : le bit 43 `AllowUnwalkableTargetTile` n'est PAS pose. `UseWholeBoard` fait
    # sauter tout test de portee (`get_range` rend None) -- la contrainte de distance de l'airstrike,
    # s'il en existe une, vivrait dans une regle DYNAMIQUE, or le preset pose ses deux delegues a 0 et
    # le bit `TargetMatchesDynamicRule` est ABSENT : le natif ne borne donc PAS la portee de ce cast.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsTile
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
    ), self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        valkyrie_strike_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        bond = next((p for n, p in ectx.emitted if n == "AddBondEffect"), None)
        return {"ability": "ValkyrieStrike", "caster": caster_id, "target": target_id,
                "deferred_effect": (bond or {}).get("effect_type", VALKYRIE_STRIKE),
                "immediate_attack": None, "dsl": True}


class CordClawAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CordClawAbility$$ExecuteBehaviour` (id 1122, admecRuststalker « Exitor-Rho », AdMech) —
    MIRROR du DECOMPILE, arbre DSL (`cord_claw_tree`) :
        Execute( op_Addition(
            AttackWithAttackDamage(caster, target, MinMaxDamage, DirectDamage, nrOfHits=GetHits(0x2f)=4),  # attaque
            AddEffect(0x4e2=1250 CordClaw_AdditionHits, source=caster, target=Self, TurnsFromRounds(2)) ) ) # self-buff

    JUMEAU d'ArmoriumCherub (1014) : même MinMax + `GetHits`=GetNumberConstant(0x2f)=4 (corps `GetHits` PARTAGE
    -- Ghidra mislabel `ArmoriumCherubAbility$$GetHits`, mais lit la config CordClaw). Le 2e volet est un
    `AddEffect` SELF (au lieu de l'`EvaluateAbilities` d'ArmoriumCherub) : pose sur le caster l'effet 0x4e2
    (DEJA porté `hits.py:CordClawAdditionalHitsEffect`, canal #179) pour `TurnsFromRounds(2)`. Attaque MELEE
    DirectDamage (PiercingRatio 100 = ignore armure). Plain `Execute` (PAS atomic).

    L'effet 0x4e2 fait gagner à TOUTES les attaques SUIVANTES du caster (i2 « All of Exitor-Rho's further
    attacks ... deal an additional 2x 582-873 Direct Damage ») +nrOfHits_2=2 coups [minDmg_2,maxDmg_2]
    DirectDamage. L'attaque DU CAST ne les gagne PAS (effet posé APRES l'attaque dans l'arbre op_add). Le
    niveau/mult des vars de l'effet sont SEEDES post-pose depuis le caster (`_seed_cord_claw_hits_level` :
    `AddEffectOperation` pose level=None ; sans seeding l'effet resoudrait ses vars au niveau 1).

    Résidu : la durée `TurnsFromRounds(2)` = 2 (identité `turns_from_rounds`, exacte en 1v1). Le residu
    d'expiration exacte (« fin de son prochain tour ») suit le cycle de vie standard des effets round."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CordClaw)  # 1122
    ABILITY_ID = "CordClaw"

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE** (la 3e des
    # trois formes) : `IdunBattleLogic.Entities.Abilities.Active.Loki.CordClawAbility$$.ctor`
    # n'appelle AUCUN `IdunBattle.Core.Services.TargetingOptions$$.ctor` -- il recopie les 0x40
    # octets du champ STATIQUE de `TargetingOptions` a l'offset RELATIF **+0x40** du bloc
    # `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 0, 0)   # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Le masque EFFECTIF est la constante ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`, soit `*(statics+0x68)`
    # = **0x4000**. Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`) -- un seul
    # bit, aucun residu :
    #     0x4000  (bit 14) TargetIsEnemy  -> PORTE (`TargetingQuery$$UnitsCanAttackEachOther`) :
    #                      refus sur soi-meme et sur un allie.
    # `TargetMatchesDynamicRule` (0x2) est ABSENT : le natif ne consulte AUCUNE regle dynamique pour
    # cette ability, quel que soit le contenu du slot vtable +0x480.
    # PORTEE : le MEME preset `+0x40` porte `TargetingRange` <- `TargetingRange` statique **+0x30**
    # (`IdunBattle.Core.Services.TargetingRange$$.cctor` : `onlyAdjacent = 0 = RangedBool.True`,
    # `useRangeFromConfig = false`, `useWholeBoard = false`, `overrideRange = Nullable(1)`) =
    # `RANGE_ADJACENT` -> le filtre statique prend la branche `battleQuery.AreEntitiesAdjacent`
    # (adjacence, PAS un `dist <= N`). Coherent avec la config : `CordClaw.constants` ne porte
    # AUCUNE cle `range` (juste `nrOfHits`/`damageProfile`/`nrOfHits_2`) et `attackRangeType` vaut
    # `Melee`. `forceMeleeTarget` (`<preset>+0x20` = `*(statics+0x60)`) = **1** = `RangedBool.False`
    # -> aucun clamp melee a poser, la portee EST deja l'adjacence.
    # ATTENTION -- MEME PRESET QUE `ThunderousAssault` (1043), MASQUE DIFFERENT : 1043 recopie AUSSI
    # `statics+0x40`, mais elle enchaine sur la surcharge « preset + flags »
    # (`TargetingOptions..ctor(&opts, &preset, 0x10000000, 0)`), qui COMBINE
    # (`dst+0x28 = flags | preset+0x28`) -> 0x10004000. CordClaw, elle, copie INTEGRALEMENT et
    # s'arrete la : son masque est le preset NU, sans `CasterCanMove`. Meme source, deux masques --
    # c'est la FORME du ctor qui tranche, pas le preset.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         self_cast=False, range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        cord_claw_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        main = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        placed = next((p.get("placed") for n, p in ectx.emitted if n == "AddEffect"), None)
        # seede niveau/mult des vars de l'effet 0x4e2 depuis le caster (AbilityStateReference native) :
        # AddEffectOperation pose level=None -> sans seeding les coups additionnels seraient au niveau 1.
        _seed_cord_claw_hits_level(state, caster_id)
        return {"ability": "CordClaw", "caster": caster_id, "target": target_id,
                "main_attack": main, "self_buff_placed": placed, "dsl": True}


def _black_rage_move_range(state, caster_id: int) -> int:
    """`IdunBattleLogic.Entities.DSLFormulas$$UnitMovementRangeWithBonus(caster@0x160, 0x53e=1342,
    ConfigConst(0xe = extraMovement))`, lu par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetPossibleMovementTiles` —
    MIRROR 1:1 (MÊME nœud, MÊME forme que `orks.py::waaagh_move_range`, seul l'EffectType diffère) :

        If( HasEffect(caster, 1342), StatAmount(caster, MOVEMENT(1), Current),
                                     Sum(<idem>, bonus) )

    ANTI-DOUBLE-COMPTE : à l'exécution de la phase C, l'effet 1342 est DÉJÀ posé (phase B `ExecuteAtomic`
    précède) -> la portée est la stat MOVEMENT *déjà bonifiée* par le stat-mod de
    `BlackRageExtraMoveEffect.applied_stat_mods` ; sinon MOVEMENT + `extraMovement`. Les deux branches
    coïncident donc, et la fidélité du stat-mod est DIRECTEMENT observable sur la portée de charge."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    stats = getattr(sc.ctx, "stats", None) if sc is not None else None
    mv = int(stats.get_stat(int(StatType.MOVEMENT), 0)) if stats is not None else 0
    has_eff = (state.effects is not None
               and state.effects.has_effect(caster_id, effect_type=BLACK_RAGE_EXTRA_MOVE))
    if has_eff:
        return mv
    bonus = ability_var("BlackRage", "extraMovement", is_constant=True) or 0   # ConfigConst(0xe) = 1
    return mv + int(bonus)


def black_rage_possible_movement_tiles_selector(move_range: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetPossibleMovementTiles` —
    MIRROR du décompilé, ARBRE DSL (plus aucune logique recâblée à la main) :

        TilesUnitCanMoveToChargeTarget( caster@0x160, casterTile@0x168, target@0x178,
                                        UnitMovementRangeWithBonus(caster, 0x53e=1342,
                                                                   ConfigConst(0xe)),
                                        ignoreFlags = 0 )
        = CanAddUnit(AdjacentTiles(target)) op_BitwiseAnd MovableTilesInRange(caster, casterTile,
                                                                              range, ignoreFlags=0,
                                                                              ignoreUnitsOnTiles=0)

    `ignoreFlags=0` (comme Waaagh ; CONTRASTE avec VigilanceEternal, qui passe 1). ⚠ #381-r1 : ce
    booléen N'EST PAS un `canReachOnly` — il ne touche que la garde d'entrée de
    `MovementQuery$$FindAnyOrAllMoveableTiles`. L'ensemble « movable » est TOUJOURS le `stop_set`
    (tuiles LIBRES), `MovementQuery$$AnyOrFillMoveableTiles` terminant par
    `RemoveAll(t => !IsMovableTile(unit, t, ignoreUnitsOnTiles=0))`.

    #206 — le pool COLLAPSÉ qui vivait ici (`board.neighbours(tuile de la cible)`, ring-1 NU) est
    SUPPRIMÉ : il ignorait `MovableTilesInRange`, donc il proposait des tuiles hors de portée de charge
    (le commentaire « la reachability est déjà garantie par la DÉCISION » ne vaut que pour l'EXISTENCE
    d'une tuile atteignable, pas pour TOUTES les voisines). Ce résidu était sans conséquence tant que le
    tri collapsé prenait la plus PROCHE du caster ; il devient décisif dès que le tri est celui du natif.

    `move_range` arrive DÉJÀ CALCULÉ (`_black_rage_move_range`) et est présenté au nœud par un `Const` :
    c'est LA valeur du 4e argument natif.

    `DSLSelectors$$TilesUnitCanMoveToChargeTarget` passe son `casterTiles` au ctor de
    `MovableTilesInRangeSelector`, dont le `Select` le resout par `TargetsSelector$$SelectTile`
    (vslot 0xc, UNE tuile -- il remplace le `GetMainTile(unit)` par defaut) : d'ou le `SelectTile`
    autour de l'accesseur d'empreinte (#459)."""
    return tiles_unit_can_move_to_charge_target(Caster(), SelectTile(CasterTile()), Target(),
                                                Const(int(move_range)), ignore_flags=False)


def _black_rage_charge_tile(state, caster_id, target_id, move_range: int):
    """Sélecteur de destination de la phase C de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour` :

        `First( SortTilesByUtility( BlackRageAbility.GetPossibleMovementTiles(),
                                    caster@0x160, 0x20 ), 1 )`

    Le littéral d'utilité est **0x20 = 32 = `UtilityType.MovementSuggestion`** (relu au décompilé :
    `SortTilesByUtility(factory, pool, caster@0x160, 0x20)` = la surcharge int de
    `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility`, qui construit `UtilityDefinition..ctor(0x20)`
    et délègue à la surcharge objet avec `ownerSel` NUL), PAS le `7 = Tile` des ports frères.
    `IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities` compose la clé `0x20` en
    `[Tile(7), TileDistance(34)]` — les DEUX enfants sont portés (#201, `engine/utilities/tile.py`).

    #206 — le COLLAPSE « tuiles ADJACENTES à la cible ordonnées par proximité au caster » est SUPPRIMÉ :
    il ne reproduisait le natif que dans le régime où `Tile(7)` est PLAT (alors `TileDistance = -d/10`,
    seul terme non nul, ordonne bien par distance croissante) et il INVERSAIT le natif dès que `Tile(7)`
    départageait — `Tile(7)` est à valeurs entières (Elevation 10/niveau, TileEffects +-9/-25) et domine
    toujours `|TileDistance| <= 0.2` sur un pool de charge. Même correction, même call-site que
    `_vigilance_move_dest_tile` / `waaagh_charge_tile` (cf.
    `docs/rl/case-201-movement-suggestion-tiledistance.md`). Renvoie une (col,row) ou None."""
    board = getattr(state, "board", None)
    if board is None or state.get_entity(caster_id) is None or state.get_entity(target_id) is None:
        return None
    cands = black_rage_possible_movement_tiles_selector(move_range).evaluate(
        entities_from_state(state, caster_id, target_id))
    if not cands:
        return None
    # `caster@0x160` = `dc.units` du sélecteur -> `case.units`, l'unité dont `TileDistanceUtility`
    # mesure l'éloignement (et que lisent les feuilles gatées sur l'unité, case-165b).
    best = first_tile_by_utility(state, cands, unit_id=caster_id,
                                 utility_type=int(UtilityType.MovementSuggestion))
    return board.coord(best) if best is not None else None


def black_rage_set_health_tree() -> SetHealth:
    """Phase A de `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour` :
    `Execute( ChangeStat(caster@0x160, Position(Health=5,0), PercentageOf(StatAmount(caster, Health, Max),
    ConfigVar(0x26 = hpPct)), mode 3 = SetAbsolute) )` =
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetSetHealthBehaviour`. Coût self :
    Lucien tombe à `hpPct` % de sa MaxHealth."""
    return SetHealth(Caster(), "BlackRage", "hpPct")


def black_rage_buffs_tree() -> AtomicGroup:
    """Phase B de `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour` :
    `ExecuteAtomic( AddStaticStatModifierEffect(caster@0x160, 0x53e, stat=MOVEMENT(1),
    ConfigConst(0xe)) & AddEffect(0x53f, AbilityStateReference, caster, caster)
    & AddEffect(0x540, <idem>) )` — 3 self-buffs, durée ZÉRO (remaining=0 live).

    ExtraMove(1342) applique +1 MOVEMENT (feuille -> `BlackRageExtraMoveEffect.applied_stat_mods`),
    ExtraDamage(1343)/AutomaticUnit(1344) = marqueurs (résidus documentés côté classe d'effet). NB :
    `AddStaticStatModifierEffect(1342)` natif est FOLDÉ dans `AddEffect(1342)` + la classe
    `BlackRageExtraMoveEffect` (qui DÉCLARE le stat-mod MOVEMENT) : même Operation `AddEffectOperation`
    en aval, même observable (statModSources). `AtomicGroup` = inline (RE #201, pass-through)."""
    return AtomicGroup(op_and(op_and(
        AddEffect(BLACK_RAGE_EXTRA_MOVE, "BlackRage_ExtraMove", Caster(), 0),        # durée 0 -> permanent (remaining=0)
        AddEffect(BLACK_RAGE_EXTRA_DAMAGE, "BlackRage_ExtraDamage", Caster(), 0)),
        AddEffect(BLACK_RAGE_AUTOMATIC_UNIT, "BlackRage_AutomaticUnit", Caster(), 0)))


def black_rage_charge_tree(dest) -> "op_and":
    """Phase C de `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour` :
    `Execute( MoveUnit(caster@0x160, First(SortTilesByUtility(GetPossibleMovementTiles, caster, 0x20), 1),
    <options nulles>) op_BitwiseAnd UseActiveAbility(Alive(caster@0x160), target@0x178,
    UnitNormalAttackType(caster)) )`.

    `MoveUnit` = la CHARGE (destination = `_black_rage_charge_tile`, calculée APRÈS la phase B pour que
    `UnitMovementRangeWithBonus` voie l'effet 1342 déjà posé, exactement comme le natif dont les
    sélecteurs sont PARESSEUX). `UseActiveAbility(Caster(), Target())` = l'attaque NORMALE au contact
    (dispatch `AttackDamageOperation.execute`, mêlée post-move). Le `Alive(caster)` natif du sujet de
    `UseActiveAbility` n'est pas modélisé (résidu : le caster ne peut pas mourir entre le move et
    l'attaque sur ce chemin — le move ne déclenche aucun overwatch, options NULLES)."""
    return op_and(MoveUnit(Caster(), FixedTiles([dest] if dest is not None else [])),
                  UseActiveAbility(Caster(), Target()))


class BlackRageAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour` (id 1163, bloodDeathCompany « Lucien », #217) — MIRROR
    du DÉCOMPILE, TROIS exécutions top-level SUCCESSIVES (`Execute` / `ExecuteAtomic` / `Execute`) :
        A. Execute( SetHealth(caster -> hpPct% MaxHealth) )   # IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetSetHealthBehaviour ; hpPct=30
        B. ExecuteAtomic( AddEffect(1342 ExtraMove) & AddEffect(1343 ExtraDamage)
                          & AddEffect(1344 AutomaticUnit) )   # 3 self-buffs
        C. Execute( MoveUnit(caster -> charge) & UseActiveAbility(caster, target, NormalAttack) )

    Sélecteurs natifs : caster = `factory+0x160`, target = `factory+0x178` (l'ENNEMI chargé). Les effets +
    SetHealth ciblent le CASTER (self) ; l'attaque NORMALE frappe la cible AU CONTACT (après la charge).

    TROIS exécutions top-level -> le contexte `entities` est RE-MATÉRIALISÉ entre chacune (l'`AbilityEntities`
    natif porte une réf d'état : les sélecteurs de l'étage N voient les mutations des étages < N), et la
    DESTINATION de charge est lue APRÈS la phase B — c'est ce qui fait voir à
    `UnitMovementRangeWithBonus(caster, 1342, extraMovement)` l'effet 1342 DÉJÀ posé (#206 ; même
    ordonnancement que `orks.py::WaaaghAbility`).

    VALIDÉ live (31337, Lucien MaxHealth 15060 vs tyranTyrantGuard) : hp 9035 -> 4518 (=30% Max), pose 1342/
    1343/1344 (remaining=0), movement +1 (statModSources source-de-l'effet), charge tuile adjacente (5,8),
    attaque normale mêlée 4 coups. RÉSIDUS documentés : +extraDmg-on-charge (négligeable, gate IsCharging non
    porté), act-again AutomaticUnit (triggered PerformAIAction non porté). L'attaque normale offline consomme
    `state.rng` (dégât bit-exact seulement si rng calé ; la SÉQUENCE reste fidèle)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BlackRage)   # 1163
    ABILITY_ID = "BlackRage"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$.ctor` :
    #     lVar1 = <statiques de `IdunBattle.Core.Services.TargetingRange`> ;
    #     <copie des 0x18 octets de `lVar1 + 0x48`>                        # preset `useWholeBoard`
    #     TargetingOptions..ctor(&opts, 0, &<copie>, 1, 0x106004012, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)
    # -> overload « FLAGS DIRECTS » (8 arguments : isSelfCasting=0, range=&preset, forceMeleeTarget=1
    # = `RangedBool.False`, rules=0x106004012), PAS l'overload « preset + flags » : le littéral EST
    # le masque effectif. Le ctor est BYTE-IDENTIQUE à celui de
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$.ctor` (même bloc de statiques,
    # même offset 0x48, même littéral) — mais il a été RELU sur BlackRage, pas hérité de Waaagh.
    # Décomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2         TargetMatchesDynamicRule        -> consulte GetDynamicInvalidTargetReason
    #     0x10        CasterHasNotMoved               -> PORTE (volet CASTER : Lucien ne peut pas
    #                                                    caster BlackRage après s'être déplacé)
    #     0x4000      TargetIsEnemy                   -> PORTE (refus sur soi-même / un allié)
    #     0x6000000   AllowObscuredTarget             -> permissif (aucune contrainte de ligne de vue)
    #     0x100000000 TargetIsNotAdjacent             -> PORTE : une cible DEJA au contact de Lucien
    #                                                    est refusée AVANT la règle dynamique
    # PORTEE (#241) : `range` = `TargetingRange` statique `+0x48` = `useWholeBoard` -> le volet
    # générique de portée NE TESTE RIEN. La contrainte de distance de BlackRage vit ENTIEREMENT dans
    # `get_dynamic_invalid_target_reason` ci-dessous (qui rend le même code `TargetIsInRange`).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.CasterHasNotMoved
        | TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
        | TR.TargetIsNotAdjacent
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state, caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetDynamicInvalidTargetReason`
        — MIRROR du décompilé :

            tiles = BlackRageAbility.GetPossibleMovementTiles()
            ents  = AbilityEntities(caster, caster, target, 0, 0, 0, casterTiles, ...)
            return Count( tiles.Evaluate(ents) ) > 0 ? 0 : 0x8000000

        `0x8000000` = `TargetingRule.TargetIsInRange` : BlackRage exprime sa contrainte de DISTANCE
        ici (et pas par le volet portée générique du filtre statique, désarmé par `useWholeBoard`).
        Le prédicat : il existe au moins une tuile LIBRE et marchable hex-adjacente à la cible,
        atteignable par le caster en `MOVEMENT + extraMovement` pas — autrement dit **la cible doit
        être chargeable ce tour-ci, sans bouger d'abord**.

        JUMEAU STRUCTUREL de `WaaaghAbility$$GetDynamicInvalidTargetReason` (même forme, même code
        rendu), à une différence de FORME près relevée au décompilé : le natif appelle ici
        `GetPossibleMovementTiles()` SANS argument (la cible est prise du sélecteur `factory+0x178`
        de l'arbre), là où Waaagh lui passe `Get(target)` — les deux voient la MEME cible, celle de
        l'`AbilityEntities` construit juste après.

        La portée est lue par `_black_rage_move_range` (= `UnitMovementRangeWithBonus(caster, 0x53e
        = 1342, ConfigConst(0xe))`) : au moment du GATE l'effet 1342 n'est PAS encore posé (aucune
        des trois phases de la behaviour n'a commencé) -> la branche `MOVEMENT + bonus` du `If`
        natif, exactement comme le natif qui évalue la même formule avant toute exécution."""
        if target_id is None or state.get_entity(int(target_id)) is None:
            return int(TR.TargetIsInRange)
        move_range = _black_rage_move_range(state, caster_id)
        tiles = black_rage_possible_movement_tiles_selector(move_range).evaluate(
            entities_from_state(state, caster_id, target_id))
        return 0 if len(tiles) > 0 else int(TR.TargetIsInRange)

    def execute_behaviour(self, state, caster_id, target_id):
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        # A) Execute(SetHealth)
        black_rage_set_health_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        # B) ExecuteAtomic(3 self-buffs) — pose 1342, qui bonifie MOVEMENT.
        black_rage_buffs_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        # C) Execute(MoveUnit & UseActiveAbility) — portée et destination LUES APRÈS le buff.
        move_range = _black_rage_move_range(state, caster_id)
        dest = _black_rage_charge_tile(state, caster_id, target_id, move_range)
        black_rage_charge_tree(dest).execute(entities_from_state(state, caster_id, target_id), ectx)
        set_hp = next((p for n, p in ectx.emitted if n == "SetHealth"), None)
        effects = [p.get("effect_type") for n, p in ectx.emitted if n == "AddEffect"]
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)
        attack = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        return {"ability": "BlackRage", "caster": caster_id, "target": target_id,
                "set_health": set_hp, "effects": effects, "moved": moved, "attack": attack, "dsl": True}


