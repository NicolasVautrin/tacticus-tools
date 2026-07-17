"""Abilities actives du namespace natif `...Abilities.Active.Loki.*` — 1 classe par ability (VA citée).

Chaque `execute_behaviour` reproduit la behaviour-seq de `<Ability>.ExecuteBehaviour` native : on appelle
les operations portées dans le MÊME ORDRE que le DSL (attaque → AddEffect → déplacements). Au scope de la
tranche EFFETS, l'étape **AddEffect** est portée+validée ; les étapes attaque/push/move (qui mutent PV /
positions) délèguent à leurs tranches (DAMAGE param-ability, déplacement) et sont marquées TODO avec leur
VA pour rester fidèle à la SÉQUENCE.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .base import ActiveAbility, turns_from_rounds, ability_attack_params
from ..operations.effects import AddEffectOperation
from ..operations.damage import AttackDamageOperation
from ..operations.spawn import SpawnUnitOperation
from ..components import StatsComponent, OwnerComponent, PositionComponent, UnitComponent
from ...entities.stats import StatType
from ...entities.effect_type import EffectType
from ...entities.active_ability_type import ActiveAbilityType  # #158 : ABILITY_TYPE -> enum (module = abilities ACTIVES)
# --- Vocabulaire DSL pour bâtir les arbres `<Ability>.ExecuteBehaviour` (#203) : les COMBINATEURS génériques
#     (`Entities.Behaviours` → entities/behaviours.py), les SÉLECTEURS/FORMULES (`Entities.Selectors`/
#     `Formulas` → entities/selectors.py + formulas.py), et les FEUILLES runner-couplées (`Entities.Behaviours`
#     liées aux Operations → runner/abilities/behaviours.py). Les arbres eux-mêmes (SPÉCIFIQUES à chaque
#     ability) vivent ICI, dans le mirror de `Abilities.Active.Loki`.
from fractions import Fraction

from ...dsl.base import Const, _round_fix64
from ...dsl.effects import ExecutionContext
from ...dsl.event_trigger_type import EventTriggerType   # #209 : EvaluateAbilities(EventTriggerType) node
from ...entities.behaviours import Seq, Foreach, If, AtomicGroup, op_add, op_and
from ...entities.selectors import (Cache, Target, Subject, get_spawn_tile_selector, Children,
                                   LastUnitAttackedBy, Caster, CasterTile, TargetTile, AdjacentEnemies,
                                   And, UnitsWithoutTrait, Union, UnitsFromFaction, AdjacentFriends, Alive)
from ...entities.formulas import TotalAttacksMade, UnitTurnsStarted
from ...entities.triggers import AmountIsGreaterThanZero, AmountIsEqual, IsAlive, TriggerAnd
from ...entities.traits.unit_trait import UnitTrait
from ...entities.effects.magnitude import ability_var
from .behaviours import (Spawn, PerformAIAttack, AddBondEffect, AttackWithAbilityDamage, AddEffect, Heal,
                         EvaluateAbilities, entities_from_state)

if TYPE_CHECKING:
    from ..state import State

# #158 : ids d'effet -> enum natif EffectType (attention same-hex : 27 = EffectType.Taunted_* ICI, PAS UnitTrait.Steppable).
STUNNED = int(EffectType.Stunned)                       # 1162 — effet COMPOSITE -> enfants 1165/1166/1167
TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)   # 27 — COMPOSITE -> 25/26/1237 ; bond
PINNED = int(EffectType.Pinned)                         # 1065 — UI « Suppressed » — stat-mod Movement
VALKYRIE_STRIKE = int(EffectType.ValkyrieStrike_Effect)  # 1022 — airstrike DIFFÉRÉ, fire au tour suivant


# ==================================================================================================
# Arbres DSL `<Ability>.ExecuteBehaviour` (namespace natif `Abilities.Active.Loki`) — SPÉCIFIQUES à
# chaque ability : ils COMPOSENT les nœuds GÉNÉRIQUES (combinateurs `entities/behaviours.py`, feuilles
# runner-couplées `behaviours.py`, sélecteurs/formules `entities/selectors.py`+`formulas.py`) en l'arbre
# EXACT du décompilé.
# (Placés ICI, avec leurs classes d'ability — PAS mélangés aux nœuds génériques réutilisables.)
# ==================================================================================================

def thunderous_assault_tree() -> AtomicGroup:
    """Arbre de `ThunderousAssaultAbility.ExecuteBehaviour @1812158b0` (id 1043, templSwordBrother — MIRROR
    du DECOMPILE) :
        ExecuteAtomic(
            AttackWithAttackDamage(caster, Units(Cache(First(Nearest(Tiles(target),casterPos)))),
                                   MinMaxDamage, profile=Power, hits=GetNumberConstant(0x2f))
          & AddEffect(0x48a Stunned, AbilityStateReference, target, TurnsFromRounds(1))
          & PushUnit(caster, target) & KillDeadUnits(...) & MoveUnit(caster, CanAddUnit) )   # DEPLACEMENT
    Port (attaque & stun ; push/kill/move = tranche DEPLACEMENT differee, no-op comme l'imperatif) :
        AtomicGroup( op_and( AttackWithAbilityDamage(Target(),"ThunderousAssault","Power",melee),
                             AddEffect(STUNNED,"Stunned",Target(),1) ) )
    `op_and` = `op_BitwiseAnd` (`CombinedBehaviour`) : effets PURS (flag@+0x20==0) -> les DEUX s'executent
    (l'attaque ne court-circuite pas le stun, meme si elle tue la cible — le stun s'applique inconditionnel-
    lement APRES, comme l'imperatif live-valide). `AtomicGroup` = inline (RE #201). Ordre = attaque PUIS stun
    (== l'imperatif, meme `state.rng`) -> bit-exact BY CONSTRUCTION. `Target()` = `ctx.target` (cible du
    message = celle que l'imperatif attaque)."""
    return AtomicGroup(op_and(
        AttackWithAbilityDamage(Target(), "ThunderousAssault", "Power", is_melee=True),
        AddEffect(STUNNED, "Stunned", Target(), 1)))


def armorium_cherub_tree() -> AtomicGroup:
    """Arbre de `ArmoriumCherubAbility.ExecuteBehaviour @1811b4000` (id 1014, adeptRetributor «Vindicta» —
    MIRROR du DECOMPILE) :
        ExecuteAtomic(
            AttackWithAttackDamage(caster, target, MinMaxDamage(minDmg 0xc/maxDmg 0xd), profile=Flame,
                                   nrOfHits=GetNumberConstant(0x2f)=4)          # 4x Flame ranged, feu posé #136
          & EvaluateAbilities(0x4b=AttackInAtomicGroup) )                       # -> passif FireOfAbsolution
    Port : `AtomicGroup( op_and( AttackWithAbilityDamage(Target(),"ArmoriumCherub","Flame",ranged),
                                 EvaluateAbilities(AttackInAtomicGroup, ranged=True) ) )`.
    `MinMaxDamage(target,0)` @180fb2dc0 = `RandomAmount(minDmg[0xc],maxDmg[0xd])` = le degat generique de la
    feuille `AttackWithAbilityDamage` (bit-exact via `ability_attack_params` ; la branche `param_3!=0` =
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
        AttackWithAbilityDamage(Target(), "ArmoriumCherub", "Flame", is_melee=False),
        EvaluateAbilities(int(EventTriggerType.AttackInAtomicGroup), ranged=True)))


def crushing_claws_splash_tree() -> Seq:
    """Corps `Func<entities,behaviour>` du `Foreach` splash = lambda `<ExecuteBehaviour>b__0 @1811e3c60`
    (DECOMPILE) pour l'unite splash COURANTE (`Subject()`, posee par le `Foreach`) :
        PushUnit(caster, s)                                          # [DEPLACEMENT differe -> omis]
        + If(IsAlive(s)) AddEffect(0x429 Pinned, stateRef, s, 0)     # « Suppressed » splash (duree DEFAUT)
        + If(IsAlive(s)) AttackWithAttackDamage(caster, s, MinMaxDamage2, GetDamageProfile2=Physical,
                                                GetNumberConstant(0x32)=nrOfHits_2)
    `If(IsAlive(Subject()))` gate le pin ET l'attaque : le natif inclut les morts-adjacents dans le SET et
    les skippe ICI (l'imperatif les pre-excluait via `_adjacent_to_both` -> MEME resultat observable).
    `PushUnit` = tranche DEPLACEMENT differee (omis, no-op comme ThunderousAssault). `op_add` = `op_Addition`
    (`CombinedBehaviour`, effets purs -> les deux volets s'executent). Volet secondaire = clés `minDmg_2`/
    `maxDmg_2`/`nrOfHits_2` (profil Physical)."""
    s = Subject()
    return op_add(
        If(IsAlive(s), AddEffect(PINNED, "Pinned", s, None)),       # duree DEFAUT (arg natif 0, sans TurnsFromRounds)
        If(IsAlive(s), AttackWithAbilityDamage(s, "CrushingClaws", "Physical", is_melee=True,
                                               min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2")))


def crushing_claws_tree() -> AtomicGroup:
    """Arbre de `CrushingClawsAbility.ExecuteBehaviour @1811cd5e0` (id 1105, tyranTyrantGuard — MIRROR du
    DECOMPILE + du lambda `<ExecuteBehaviour>b__0 @1811e3c60`) :
        splash = UnitsWithoutTrait( AdjacentEnemies(caster) & (AdjacentFriends(target) - target), 0xd=Object )
        ExecuteAtomic(
            ((  AddBondEffect(0x1b Taunted, caster, target, TurnsFromRounds(1))            # taunt cible
              + AddEffect(0x429 Pinned, target, DEFAUT) )                                  # « Suppressed » cible
              + AttackWithAttackDamage(caster, target, MinMaxDamage, Piercing, 0x2f=2) )   # attaque principale
            + Foreach(splash, crushing_claws_splash_tree) )
    Port mirror-natif. `AdjacentEnemies(caster) & (AdjacentFriends(target) - target)` = ennemis du caster
    adjacents aux DEUX (les amis de la cible = ennemis du caster) -> convention ETABLIE Harvester
    (`AdjacentEnemies(<tile>)` = ennemis-du-caster autour de <tile>, active_ability.py) :
    `And(AdjacentEnemies(CasterTile()), AdjacentEnemies(TargetTile()))` — chaque centre s'auto-exclut
    (`_within` d>0), donc target/caster hors splash. `UnitsWithoutTrait(Object=13=0xd)` exclut la scenerie
    (0xd MAPPE UnitTrait.Object #158 ; l'imperatif le SKIPPAIT -> le DSL est PLUS fidele, degrade en no-op
    pour une unite sans le trait). ORDRE natif = taunt, pin, main, foreach (l'imperatif faisait main
    d'abord ; equivalent bit-exact : taunt/pin ne tirent PAS de rng et n'affectent pas le degat principal ->
    MEME sequence rng). `KillDeadUnits`/`MoveUnit`/`PushUnit` = tranche DEPLACEMENT differee (omis). Duree
    Pinned = DEFAUT (`duration_rounds=None`). Bit-exact BY CONSTRUCTION (memes Operations/args/state.rng que
    l'imperatif). L'imperatif `CrushingClawsAbility.execute_behaviour` est REMPLACE par l'execution de l'arbre."""
    tgt = Target()
    taunt = AddBondEffect(TAUNTED, "Taunted_OnlySpecificTargets", Caster(), tgt, 1)   # AddBondEffect(0x1b)
    pin = AddEffect(PINNED, "Pinned", tgt, None)                                       # AddEffect(0x429), duree DEFAUT
    main = AttackWithAbilityDamage(tgt, "CrushingClaws", "Piercing", is_melee=True)    # MinMaxDamage/Piercing/0x2f=2
    splash = UnitsWithoutTrait(
        And(AdjacentEnemies(CasterTile(), Const(1)), AdjacentEnemies(TargetTile(), Const(1))),
        int(UnitTrait.Object))                                                          # UnitsWithoutTrait(0xd)
    return AtomicGroup(op_add(
        op_add(op_add(taunt, pin), main),                                             # ((taunt+pin)+main)
        Foreach(splash, crushing_claws_splash_tree())))                               # + foreach(splash)


def spirit_leech_get_attack_damage(state, caster_id, target_id, bmin, bmax):
    """`SpiritLeechAbility.GetAttackDamage @181209dd0` (COMBAT, param_3=0), MIRROR du DECOMPILE :
        ConditionalAmount( NOT HasEffect(target, Pinned 0x429), MinMaxDamage, MinMaxDamage + extraDmg )
    = si la cible est DEJA Pinned/« Suppressed » -> base + `extraDmg` (ConfigVar 8) ; sinon base seule.
    Le bonus est FLAT sur les 2 bornes AVANT le tirage per-coup. `extraDmg` est DANS
    `variablesAffectedByRarityBonus` -> multiplier = `AbilityVariablesMultiplierPercentage` du caster
    (contrairement a `hpToHealPct`, brut). Passe en `damage_override` a `AttackWithAbilityDamage` (le natif
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
    `LastAttackDamageMade` = total (degat SANTE) de la DERNIERE `AttackWithAbilityDamage` emise (lu dans
    `ectx.emitted` = le seul volet d'attaque de SpiritLeech). `hpToHealPct` est HORS
    `variablesAffectedByRarityBonus` -> valeur brute par niveau (multiplier 100). `PercentageOf` natif passe
    `mode=1` = CEILING (`_round_fix64`, node canonique `entities/formulas.py`) : `ceil(total x pct/100)`
    (== `PercentageOf.Calculate`) — l'ancien imperatif tronquait (`int`), corrige ici au decompile."""
    total = 0
    for name, p in ectx.emitted:
        if name == "AttackWithAbilityDamage":
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


def spirit_leech_tree() -> Seq:
    """Arbre de `SpiritLeechAbility.ExecuteBehaviour @181209900` (id 1104, tyranNeurothrope — MIRROR du
    DECOMPILE) :
        Execute( op_Addition( op_Addition( op_Addition(
            AttackWithAbilityDamage(self, target, GetAttackDamage, Psychic, nrOfHits=0x2f=1),   # [A] attaque
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
    attack = AttackWithAbilityDamage(tgt, "SpiritLeech", "Psychic", is_melee=False,   # ranged (range 3), nrOfHits=0x2f=1
                                     damage_override=spirit_leech_get_attack_damage)  # GetAttackDamage (+extraDmg si Pinned)
    pin = AddEffect(PINNED, "Pinned", tgt, None)                                      # AddEffect(0x429), duree DEFAUT
    heal = Heal(spirit_leech_heal_targets(), spirit_leech_heal_amount)                # lifesteal (Self + Tyranids adj)
    return op_add(op_add(attack, pin), heal)                                          # ((A + Pin) + Heal)


def plasma_grenade_tree():
    """Arbre de `PlasmaGrenadeAbility.ExecuteBehaviour @1811f99e0` (id 1098, eldarSmnGuardian — MIRROR du
    DECOMPILE) :
        Execute( op_Addition(
            AttackWithAbilityDamage(caster, target, RandomAmount(minDmg=var0xc, maxDmg=var0xd), Plasma,
                                    nrOfHits=GetNumberConstant(0x2f)),                        # [MAIN]
            AttackWithAbilityDamage(caster, Enemies(caster, AdjacentUnits(target,1)), RandomAmount(MEME),
                                    Plasma, nrOfHits_2=GetNumberConstant(0x32)) ) )           # [SPLASH]
    Port : `op_add(main, splash)`. Le SPLASH natif passe un SELECTEUR MULTI-cible directement a UN
    `AttackWithAbilityDamage` (PAS un `Foreach`) -> `AttackBehaviour.Execute @180fb91a0` resout la liste,
    l'`OrderBy` puis attaque chaque cible : porte via `multi=True` (feuille `AttackWithAbilityDamage`, tri
    par id = ordre de lecture natif). Selecteur splash = `Alive(AdjacentEnemies(TargetTile()))` = ennemis
    VIVANTS du caster adjacents (hex) a la CIBLE (`AdjacentEnemies(<tuile>)` = ennemis-du-caster autour de
    <tuile>, convention Harvester/CrushingClaws ; `Alive` = compense l'inclusion des cadavres offline, mirror
    du fait que le natif `Units(AdjacentTiles)` n'a que les unites DEBOUT = vivantes, cf. `AllUnits`=alive
    #202). La plage `RandomAmount(minDmg/maxDmg)` est PARTAGEE main/splash (memes cles config par defaut) ;
    seule la constante de coups differe (nrOfHits vs nrOfHits_2 = 0x2f/0x32). Profil Plasma, ranged (range 2).
    `op_Addition` = effets purs -> les deux volets s'executent ; plain `Execute` (PAS ExecuteAtomic). Bit-exact
    BY CONSTRUCTION vs l'imperatif `_splash_ability_behaviour` (memes bornes/hits/profil, splash `sorted` par
    id, meme `state.rng`). L'imperatif `PlasmaGrenadeAbility.execute_behaviour` est REMPLACE par cet arbre."""
    tgt = Target()
    main = AttackWithAbilityDamage(tgt, "PlasmaGrenade", "Plasma", is_melee=False)         # RandomAmount/Plasma/0x2f
    splash = AttackWithAbilityDamage(Alive(AdjacentEnemies(TargetTile())), "PlasmaGrenade", "Plasma",
                                     is_melee=False, hits_key="nrOfHits_2", multi=True)     # MEME plage, 0x32
    return op_add(main, splash)


def getemruntz_taunt_tree() -> If:
    """Corps `Func<entities,behaviour>` de `TauntWithNewChildrenWhoDidDamage @1811e27a0` (DECOMPILE) pour
    l'enfant COURANT (`Subject()`, pose par le `Foreach(Children)`) :
        If( AmountIsGreaterThanZero(TotalAttacksMade(child))            # le grot a attaque
            & AmountIsEqual(capturedTurns, UnitTurnsStarted(child))     # enfant NEUF de ce cast
            & IsAlive(LastUnitAttackedBy(child)),                       # l'ennemi frappe est vivant
            AddBondEffect(0x1b Taunted, source=child, target=LastUnitAttackedBy(child), TurnsFromRounds(1)) )
    `op_BitwiseAnd` (2x) = `TriggerAnd`. Nœud STATIQUE (lit `Subject()` a l'eval) -> passe en body de
    `Foreach`. `capturedTurns` = `Const(0)` (owner fraichement, cf. `UnitTurnsStarted`)."""
    child = Subject()
    cond = TriggerAnd(
        TriggerAnd(AmountIsGreaterThanZero(TotalAttacksMade(child)),
                   AmountIsEqual(Const(0), UnitTurnsStarted(child))),
        IsAlive(LastUnitAttackedBy(child)))
    return If(cond, AddBondEffect(TAUNTED, "Taunted_OnlySpecificTargets",
                                  child, LastUnitAttackedBy(child), 1))


def getemruntz_tree() -> Seq:
    """Arbre COMPLET de `GetEmRuntzAbility.ExecuteBehaviour @1811e2210` (id 1045, MIRROR 1:1 du DECOMPILE) :
        cache = Cache(GetSpawnTileSelector @1811e26b0)             # @180deb0d0 -- PARTAGE Spawn/Attack (memoise)
        ExecuteAtomic( Spawn(cache) )                             # @180fb0930 inline -> grots materialises
        Execute( op_Addition( PerformAIAttackFromCurrentPosition(cache),   # les grots (sur les tuiles cache) attaquent
                              Foreach(Children, Taunt) ) )        # + Taunt de la cible frappee
    Port : `Seq(AtomicGroup(Spawn(cache)), op_add(PerformAIAttack(cache), Foreach(Children(), taunt)))`.
    Le `cache` est PARTAGE entre `Spawn` et `PerformAIAttack` (mirror natif : le MEME `Cache(GetSpawnTileSelector)`
    est passe aux deux nœuds) -> memoise les tuiles LIBRES PRE-spawn (RE #200 : le CacheSelector memoise ;
    sans ca `PerformAIAttack` relirait `CanAddUnit` post-spawn et exclurait les tuiles occupees par les grots).
    `AtomicGroup` = inline (RE #201 : `AtomicGroupOperation.Execute` invoque son child sur-le-champ, PAS
    differe). `op_add`/`Seq` = `CombinedBehaviour` (effets PURS -> pas de court-circuit -> les 3 volets
    s'executent). Ordre = tous les spawns (inline dans l'AtomicGroup) PUIS toutes les attaques PUIS tous les
    Taunts (NATIF, prouve RE #200). CONFRONTE LIVE (tracer-v2 DSLFactory #200 : arbre natif capture == ce
    mirror) ; l'imperatif `SpawnUnitOperation.execute_getemruntz` a ete RETIRE (#199)."""
    cache = Cache(get_spawn_tile_selector())                       # @180deb0d0 -- PARTAGE (memoise pre-spawn)
    return Seq(
        AtomicGroup(Spawn(cache, "GetEmRuntz")),                   # ExecuteAtomic(Spawn(cache)) -- inline
        op_add(PerformAIAttack(cache),                             # Execute( op_Addition(
               Foreach(Children(), getemruntz_taunt_tree())))      #   PerformAIAttack(cache), Foreach(Children, Taunt) ))


def _summon_on_appearance_attack(state: "State", summon_id: int, target_id: int,
                                 profile_name):
    """`PerformAIAttack` à l'apparition : le summon attaque la cible. Profil = `unitDamageProfile` de
    l'ability de summon (ex. Piercing) en OVERRIDE de l'arme normale (i2 « immediately attack using
    Piercing ; subsequent attacks use their normal type »). base = stat Attack du summon, hits = arme du
    summon, pipeline normal (reduce-then-roll). No-op si rng non calé (return None)."""
    import gameconfig as GC
    e = state.get_entity(summon_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    dp = GC.damage_profile(profile_name) or {}
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + int(ctx.extra_pierce)))
    hits = max(1, int(ctx.normal_weapon_hits))
    return AttackDamageOperation.execute_normal_like(
        state, summon_id, target_id, int(ctx.stat(StatType.ATTACK)), pierce, hits=hits, spread_pct=20,
        damage_profile=profile_name, is_melee=ctx.is_melee)


class ThunderousAssaultAbility(ActiveAbility):
    """`ThunderousAssaultAbility.ExecuteBehaviour` @1812158b0 (id 1043, templSwordBrother).

    Séquence native (`&` = op_BitwiseAnd), MIGRÉE en ARBRE DSL (#203, `thunderous_assault_tree()`) :
        AttackWithAttackDamage(caster, Units(Cache(First(Nearest(Tiles(target),casterPos)))),
                               MinMaxDamage, profile=Power, hits=GetNumberConstant(0x2f))   # ← DSL
      & AddEffect(0x48a Stunned, source=casterStateRef, TurnsFromRounds(1))                 # ← DSL
      & PushUnit(target, 1 hex) & KillDeadUnits & MoveUnit(caster -> hex libéré)   # [déplacement — TODO]
    Le behaviour est l'arbre DSL (`AtomicGroup(op_and(AttackWithAbilityDamage, AddEffect))`) : les feuilles
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
        atk = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAbilityDamage"), None)
        return {"attack": atk, "dsl": True}


class ArmoriumCherubAbility(ActiveAbility):
    """`ArmoriumCherubAbility.ExecuteBehaviour @1811b4000` (id 1014, adeptRetributor «Vindicta»), MIGRÉ en
    ARBRE DSL (#209, `armorium_cherub_tree()`) :
        ExecuteAtomic(
            AttackWithAttackDamage(caster, target, MinMaxDamage(minDmg/maxDmg[level]), Flame,
                                   nrOfHits=GetNumberConstant(0x2f)=4)          # ← DSL (feuille AttackWithAbilityDamage)
          & EvaluateAbilities(0x4b=AttackInAtomicGroup) )                       # ← DSL (nœud EvaluateAbilities)
    Actif RANGED (range 2). Profil Flame (`OnFire`) → POSE du feu sur la tuile-cible via le vecteur after-hit
    d'ability (`execute_ability_attack` → `_on_fire_damage_ability`, #136). i2 « Using Armorium Cherub does
    not end Vindicta's turn » = turn-flow (ne consomme pas le tour) — NON modélisé ici (concern turn-order).

    Le behaviour est l'arbre DSL : la feuille `AttackWithAbilityDamage` émet la MÊME Operation que l'ancien
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
        main = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAbilityDamage"), None)
        passive = next((p["results"] for n, p in ectx.emitted if n == "EvaluateAbilities"), [])
        return {"ability": "ArmoriumCherub", "caster": caster_id, "target": target_id,
                "main_attack": main, "fire_of_absolution": passive, "dsl": True}


class ScarabHiveAbility(ActiveAbility):
    """`ScarabHiveAbility.ExecuteBehaviour` @181204cb0 (id 1007, necroSpyder — le SUMMONER).

    Séquence native :
        Spawn(visualId = constants["unitId"] = necroSmnSwarm,
              tile = First(SortByDistance(CanAddUnit(AdjacentTiles(target@0x178)), self@0x160)), # libre, adj. CIBLE
              owner+stats = SpawnUnitOptions.WithStatsFromConfig(config),    # team+player caster, stats ability_var
              effet = AddEffect(0x4a3 = ScarabHive_OverrideDamageProfileEffect),
              onAppearance = UseNormalAttackIfAble)                          # attaque normale immédiate
        × COUNT (2, arg du .ctor AActiveAbility)
    Stats du summon = `ability_var(ScarabHive, summonHp/summonDmg/…, casterActiveAbilityLevel, mult)`.
    À l'apparition chaque summon attaque la cible avec le profil `unitDamageProfile` (Piercing) en
    override de son arme Energy (i2). VALIDÉ live : 2× necroSmnSwarm team/player du caster, hp/attack
    bit-exact (cf. test_summon_spawn_live) ; wiring message + on-appearance (cf. test_summon_trigger_live).

    ⚠ DISTINCT de `ScarabSummonAbility` @181205290 (id 1047) = l'auto-DÉDOUBLEMENT porté par le scarab
    SPAWNÉ lui-même (spawn adjacent à SOI, stats clonées du parent via CopyOwner, on-appearance
    PerformAIAttack). NON encore porté (cf. commentaire GAP plus bas). Ne PAS confondre les deux (même
    unitId necroSmnSwarm, mais summoner-scaled vs clone-du-parent)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ScarabHive)  # 1007
    SUMMON_ABILITY = "ScarabHive"     # clé gameconfig (constants.unitId/unitDamageProfile + summon* variables)
    COUNT = 2                         # nb d'invocations (arg .ctor ; le count GÉNÉRAL est par-ability)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        import gameconfig as GC
        if target_id is None:
            return None
        consts = (GC.ability(self.SUMMON_ABILITY) or {}).get("constants") or {}
        visual_id = consts.get("unitId")
        if visual_id is None:
            return None
        # [Spawn] CopyOwner + placement adjacent-cible + stats ability_var (cf. SpawnUnitOperation).
        spawned = SpawnUnitOperation.execute(
            state, caster_id, target_id, self.SUMMON_ABILITY, visual_id, self.COUNT)
        # [on-appearance] PerformAIAttack : chaque summon attaque la cible (profil Piercing override).
        prof = consts.get("unitDamageProfile")
        attacks = []
        for sid in spawned:
            res = _summon_on_appearance_attack(state, sid, target_id, prof)
            if res is not None:
                attacks.append({"summon": sid, "total": res.get("total")})
        return {"summon": visual_id, "spawned": spawned, "attacks": attacks}


def _nearest_enemy(state: "State", unit_id: int) -> Optional[int]:
    """Ennemi VIVANT le plus proche (distance hex) de `unit_id` — cible de `PerformAIAttack` (approx du
    choix AI natif). None si pas de position/board ou aucun ennemi. Tie-break `id` (déterministe)."""
    import hexgeo
    e = state.get_entity(unit_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    if pc is None or oc is None:
        return None
    src = (pc.col, pc.row)
    best = None
    best_key = None
    for eid, o in state.entities.items():
        if eid == unit_id:
            continue
        ooc = o.get_component(OwnerComponent)
        ouc = o.get_component(UnitComponent)
        opc = o.get_component(PositionComponent)
        if ooc is None or opc is None or ooc.team == oc.team:      # ennemis uniquement
            continue
        if ouc is not None and not ouc.alive:
            continue
        key = (hexgeo.distance(src, (opc.col, opc.row)), eid)
        if best_key is None or key < best_key:
            best_key, best = key, eid
    return best


class ScarabSummonAbility(ActiveAbility):
    """`ScarabSummonAbility.ExecuteBehaviour @181205290` (id 1047, necroSmnSwarm — auto-DÉDOUBLEMENT).

    Le scarab s'invoque LUI-MÊME (« Summons another Scarab Swarm ... which then immediately takes a turn ») :
        Spawn(visualId = constants["unitId"] = necroSmnSwarm,
              tile = PickRandomly(CanAddUnit(AdjacentTiles(self@0x160))),   # libre, adjacent à SOI
              owner+stats = SpawnUnitOptions.CopyOwner(caster),             # clone du parent (owner + stats)
              onAppearance = PerformAIAttack(1))                            # le DOUBLE attaque immédiatement
        × COUNT (1)
    Stats = CLONE du parent (`CopyOwner @180fd5ba0` copie {Attack,Move,Health,Armor,20} ; le reste = config
    base necroSmnSwarm = identique au parent) → `SpawnUnitOperation.execute_self_replica`. On-appearance :
    le double attaque l'ennemi le plus proche (approx de `PerformAIAttack` ; cible AI-exacte = raffinement).
    Chance gameconfig = 50 ; playbook `ScarabSummonPlaybook`. GAP : cap de duplication
    (`UnitDuplicationLimitSelector`/`LimitUnitDuplications`) non porté (récurrence non bornée offline)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ScarabSummon)  # 1047
    SUMMON_ABILITY = "ScarabSummon"     # clé gameconfig (constants.unitId = necroSmnSwarm)
    COUNT = 1

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        import gameconfig as GC
        consts = (GC.ability(self.SUMMON_ABILITY) or {}).get("constants") or {}
        visual_id = consts.get("unitId")
        if visual_id is None:
            return None
        # [Spawn] adjacent-à-soi + CopyOwner (clone du parent), cf. SpawnUnitOperation.execute_self_replica.
        spawned = SpawnUnitOperation.execute_self_replica(state, caster_id, visual_id, self.COUNT)
        # [on-appearance] PerformAIAttack : chaque double attaque immédiatement l'ennemi le plus proche.
        # Le dégât consomme `state.rng` (roll) -> no-op gracieux si rng non calé (mirror `_summon_on_
        # appearance_attack` : la SÉQUENCE reste fidèle, seul le tirage est différé au flux runner calé).
        attacks = []
        if state.rng is not None:
            for sid in spawned:
                tgt = _nearest_enemy(state, sid)
                if tgt is not None:
                    r = AttackDamageOperation.execute(state, sid, tgt)
                    if r is not None:
                        attacks.append({"summon": sid, "target": tgt, "total": r.get("total")})
        return {"summon": visual_id, "spawned": spawned, "attacks": attacks, "replica": True}


class GetEmRuntzAbility(ActiveAbility):
    """`GetEmRuntzAbility.ExecuteBehaviour @1811e2210` (id 1045, orksRuntherd/Snotflogga). Spawn UN grot par
    hex LIBRE adjacent au caster **ET** adjacent à un ennemi, chaque grot attaque à l'apparition
    (`PerformAIAttackFromCurrentPosition`) puis Taunte l'ennemi frappé (`TauntWithNewChildrenWhoDidDamage`).

    #149 slice-2b : la behaviour EST l'**arbre DSL** `getemruntz_tree()` (mirror 1:1 du décompilé
    @1811e2210 : `ExecuteAtomic(Spawn) ; Execute(PerformAIAttack + Foreach(Children, Taunt))`), en
    remplacement du portage impératif (spawn + on-appearance + Taunt câblés à la main). **PROUVÉ bit-exact**
    (replay-diff DSL == impératif) puis **CONFRONTÉ LIVE** (tracer-v2 DSLFactory #200 : arbre natif capturé
    == ce mirror, cf. docs/rl/dsl-effect-nodes.md). L'impératif `SpawnUnitOperation.execute_getemruntz` a été
    **RETIRÉ** (#199) — la behaviour est le seul arbre DSL."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GetEmRuntz)  # 1045

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # behaviour = arbre DSL (couche effet-nœuds) ; les feuilles émettent les MÊMES Operations que
        # l'impératif (`AttackDamageOperation`/`AddEffectOperation`/`_spawn_config_grot`) -> même mutation.
        ectx = ExecutionContext(state=state, rng=state.rng)
        getemruntz_tree().execute(entities_from_state(state, caster_id), ectx)
        # diag depuis les émissions de l'arbre (mêmes champs que l'ancien retour impératif)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = next((p["attacks"] for n, p in ectx.emitted if n == "PerformAIAttack"), [])
        taunted = [p["target"] for n, p in ectx.emitted if n == "AddBondEffect"]
        return {"summon": "orksGrot", "spawned": spawned, "attacks": attacks, "taunted": taunted,
                "getemruntz": True, "dsl": True}


def _adjacent_to_both(state: "State", caster_id: int, target_id: int) -> list[int]:
    """Splash CrushingClaws : ennemis VIVANTS du caster adjacents (hex) **À LA FOIS** au caster ET à la
    cible, hors cible. Mirror `GetAdjacentDamageTargetsUnits` @1811cdad0 =
    `AdjacentEnemies(actor) & (AdjacentFriends(target) - target)` (les amis de la cible = ennemis du
    caster ⇒ ennemis adjacents aux deux). Requiert `state.board` (evenq). ⚠ exclusion
    `UnitsWithoutTrait(0xd=13)` NON portée (mapping de l'enum trait 13 inconnu offline) → TODO ; sans
    board → [] (no-op fidèle)."""
    board = state.board
    caster = state.get_entity(caster_id)
    tgt = state.get_entity(target_id)
    if board is None or caster is None or tgt is None:
        return []
    cp = caster.get_component(PositionComponent)
    tp = tgt.get_component(PositionComponent)
    co = caster.get_component(OwnerComponent)
    if cp is None or tp is None or co is None:
        return []
    ctile = board.id_at(cp.col, cp.row)
    ttile = board.id_at(tp.col, tp.row)
    if ctile is None or ttile is None:
        return []
    c_neigh = set(board.neighbours(ctile))
    t_neigh = set(board.neighbours(ttile))
    out: list[int] = []
    for eid, e in state.entities.items():
        if eid == caster_id or eid == target_id:
            continue
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or pc is None or oc.team == co.team:        # ennemis du caster uniquement
            continue
        if uc is not None and not uc.alive:
            continue
        tile = board.id_at(pc.col, pc.row)
        if tile in c_neigh and tile in t_neigh:                   # adjacent au caster ET à la cible
            out.append(eid)
    return sorted(out)                                            # ordre déterministe (tie-break id)


def _adjacent_enemies_of(state: "State", caster_id: int, target_id: int) -> list[int]:
    """Splash cible-centré : ennemis VIVANTS du caster adjacents (hex) à la CIBLE, hors cible. Mirror
    `Enemies(caster, AdjacentUnits(target))` = les ennemis du caster sur `board.neighbours(target tile)`.
    Requiert `state.board` (evenq) ; sans board → [] (no-op fidèle). Ordre déterministe (tie-break id).
    (Volet splash de PlasmaGrenade/Stikkbomb ; base de tuiles de Fragstorm avant PickRandomly.)"""
    board = state.board
    caster = state.get_entity(caster_id)
    tgt = state.get_entity(target_id)
    if board is None or caster is None or tgt is None:
        return []
    co = caster.get_component(OwnerComponent)
    tp = tgt.get_component(PositionComponent)
    if co is None or tp is None:
        return []
    ttile = board.id_at(tp.col, tp.row)
    if ttile is None:
        return []
    t_neigh = set(board.neighbours(ttile))
    out: list[int] = []
    for eid, e in state.entities.items():
        if eid == caster_id or eid == target_id:
            continue
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or pc is None or oc.team == co.team:        # ennemis du caster uniquement
            continue
        if uc is not None and not uc.alive:
            continue
        if board.id_at(pc.col, pc.row) in t_neigh:                # adjacent à la cible
            out.append(eid)
    return sorted(out)


def _pick_randomly_n(state: "State", items: list, n: int) -> list:
    """`PickRandomly(items, n)` — n éléments DISTINCTS (extension de `_pick_randomly` spawn.py à n). len<=n
    → tous (le natif ne roll pas quand le set tient). Sinon tire n index SANS REMISE via `next_internal`
    (coût/ordre RNG NON calibré → GAP flaggé : désync possible de `state.rng` ; cf. spawn.py). `state.rng`
    None → subset trié déterministe `[:n]` (placement RNG-exact = raffinement, structure d'abord)."""
    items = list(items)
    n = max(0, int(n))
    if len(items) <= n:
        return items
    if state.rng is None:
        return items[:n]
    pool, out = list(items), []
    for _ in range(n):
        out.append(pool.pop(state.rng.next_internal(0, len(pool))))
    return out


def _splash_ability_behaviour(state: "State", caster_id: int, target_id: int, ability_id: str,
                              profile: str, ranged: bool, splash_set: list) -> dict:
    """Mécanique partagée B1 (mirror `CrushingClaws` SANS var-séparées) : 1 attaque MAIN sur `target`
    (hits=`nrOfHits`) + 1 volet SPLASH sur `splash_set`, PARTAGEANT la MÊME plage `minDmg/maxDmg` — seul le
    nb de hits diffère (splash = `nrOfHits_2`). ⚠ le splash réutilise minDmg/maxDmg/pierce (PAS
    minDmg_2/maxDmg_2 : ce pattern var-séparées = CrushingClaws only). Chaque volet = `execute_ability_attack`."""
    bmin, bmax, pierce, hits = ability_attack_params(state, caster_id, ability_id, profile, ranged=ranged)
    main = AttackDamageOperation.execute_ability_attack(state, caster_id, target_id, bmin, bmax, pierce, hits,
                                                        damage_profile=profile, is_melee=not ranged)
    # splash : MÊME plage (minDmg/maxDmg/pierce), seule la constante de hits change (nrOfHits_2).
    _bmin2, _bmax2, _pierce2, hits2 = ability_attack_params(
        state, caster_id, ability_id, profile, ranged=ranged, hits_key="nrOfHits_2")
    splash: list[dict] = []
    for sid in splash_set:
        satk = AttackDamageOperation.execute_ability_attack(state, caster_id, sid, bmin, bmax, pierce, hits2,
                                                            damage_profile=profile, is_melee=not ranged)
        splash.append({"target": sid, "attack": satk})
    return {"main_attack": main, "splash": splash, "hits_main": hits, "hits_splash": hits2}


class CrushingClawsAbility(ActiveAbility):
    """`CrushingClawsAbility.ExecuteBehaviour` @1811cd5e0 (id 1105, tyranTyrantGuard).

    Séquence native (`&`/`+` = compositions de behaviour) :
        AttackWithAttackDamage(actor, target, MinMaxDamage, profile=Piercing, nrOfHits=const 0x2f=2)  # principale
      & AddBondEffect(0x1b=27 Taunted, TurnsFromRounds(1))         # Taunt cible (COMPOSITE → 25/26/1237)
      & AddEffect(0x429=1065 Pinned, target)                       # « Suppressed » cible (DefaultRounds=1)
      & Foreach(splash = AdjacentEnemies(actor) & (AdjacentFriends(target) − target), UnitsWithoutTrait(0xd)):
            PushUnit(actor, s)                                     # recul 1 hex  [déplacement — TODO]
          + If(alive) AddEffect(0x429 Pinned, s)                   # « Suppressed » splash
          + If(alive) AttackWithAttackDamage(actor, s, MinMaxDamage2, profile2=Physical, nrOfHits=const 0x32=1)

    Matérialise (vecteur ATTAQUE, tranche EFFETS) : la CIBLE porte Taunted(27)+enfants 25/26/1237 +
    Pinned(1065) ; chaque unité splash subit 1× Physique + Pinned(1065). Le **push** (déplacement, recul
    1 hex) et `KillDeadUnits`/`MoveUnit` = tranche DEPLACEMENT différée (omis, cf. ThunderousAssault).

    #149 slice-4 : `execute_behaviour` DÉLÈGUE à `crushing_claws_tree()` (mirror 1:1 du décompilé +
    lambda `<ExecuteBehaviour>b__0`). L'exclusion **trait 0xd** du splash (`UnitsWithoutTrait(Object=13)`)
    est désormais PORTÉE (0xd mappé `UnitTrait.Object` #158) — plus fidèle que l'ancien impératif qui la
    skippait. Splash gated `If(IsAlive(s))` (pin + attaque). Bit-exact BY CONSTRUCTION."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CrushingClaws)  # 1105
    ABILITY_ID = "CrushingClaws"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        crushing_claws_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAbilityDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]   # cibles splash != cible principale
        return {"ability": "CrushingClaws", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


class SpiritLeechAbility(ActiveAbility):
    """`SpiritLeechAbility.ExecuteBehaviour @181209900` (id 1104, tyranNeurothrope — MIRROR du DECOMPILE) :
        Execute( op_Addition( op_Addition( op_Addition(
            AttackWithAbilityDamage(self, target, GetAttackDamage, Psychic, nrOfHits=0x2f=1),   # attaque
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
            if name == "AttackWithAbilityDamage":
                main = p.get("attack")                            # LastAttackDamageMade (le seul volet d'attaque)
            elif name == "Heal":
                heal_amount = p.get("amount") or 0
                heals = p.get("heals") or []
        return {"ability": "SpiritLeech", "caster": caster_id, "target": target_id,
                "main_attack": main, "suppressed_bonus": suppressed,
                "heal_amount": heal_amount, "heals": heals, "dsl": True}


class ValkyrieStrikeAbility(ActiveAbility):
    """`ValkyrieStrikeAbility.ExecuteBehaviour` @181229e40 (id 1018, astraSmnVoxcaster).

    Séquence native = UNIQUEMENT `AddBondEffect(0x3fe=1022 ValkyrieStrike_Effect, caster↔target,
    DefaultRounds(1022)=0 → fallback 1 round)` — AUCUNE attaque immédiate. Le Blast `minDmg/maxDmg`
    (constants.damageProfile=Blast, nrOfHits=1) est le PAYLOAD de l'airstrike DIFFÉRÉ : l'effet 1022 fire
    au tour suivant (frappe aérienne), PAS au cast.

    ⚠ PORT DÉDIÉ = correction d'un SUR-TIR. 1018 a `constants.damageProfile` → `_is_attack_ability` renvoie
    True → le chemin GÉNÉRIQUE de `summon_ai._apply_active_ability` TIRERAIT à tort un Blast IMMÉDIAT. En
    l'enregistrant ici (handler `ported=True`), on EXCLUT 1018 du générique : le cast ne fait QUE poser
    l'effet différé (fidèle). L'airstrike différé lui-même (fire du 1022 → dégât) = sa propre tranche
    pending-effect (TODO)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ValkyrieStrike)  # 1018

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # [AddBondEffect] 1022 caster↔target (bond : source=caster capture la direction). PAS de dégât immédiat.
        AddEffectOperation.execute(state, source=caster_id, target=target_id,
                                   effect_type=VALKYRIE_STRIKE, name="ValkyrieStrike_Effect")
        return {"ability": "ValkyrieStrike", "caster": caster_id, "target": target_id,
                "deferred_effect": VALKYRIE_STRIKE, "immediate_attack": None}


class PlasmaGrenadeAbility(ActiveAbility):
    """`PlasmaGrenadeAbility.ExecuteBehaviour @1811f99e0` (id 1098, eldarSmnGuardian).

    Séquence native (`+` = op_Addition, plain `Execute`) :
        AttackWithAbilityDamage(actor, target, RandomAmount(minDmg/maxDmg), Plasma, nrOfHits=0x2f)   # principale
      + AttackWithAbilityDamage(actor, Enemies(caster, AdjacentUnits(target,1)), MÊME RandomAmount,
                                Plasma, nrOfHits_2=0x32)                                              # splash multi-cible
    Splash = ennemis adjacents (hex) à la CIBLE, plage de dégât PARTAGÉE (seul le nb de hits change).
    Ranged (range 2).

    #149 slice-6 : `execute_behaviour` DÉLÈGUE à `plasma_grenade_tree()` (mirror 1:1 du décompilé). Le
    SPLASH est un SEUL `AttackWithAbilityDamage(selecteur-multi)` (== le natif, PAS un `Foreach`) porté via
    le mode `multi=True` de la feuille (`AttackBehaviour.Execute` résout la liste + `OrderBy` par id).
    L'ancien `_splash_ability_behaviour`/`_adjacent_enemies_of` reste partagé par Stikkbomb/Fragstorm
    (non encore migrés). Bit-exact BY CONSTRUCTION vs l'impératif (mêmes bornes/hits/profil, splash trié par
    id, même `state.rng`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.PlasmaGrenade)  # 1098
    ABILITY_ID = "PlasmaGrenade"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        plasma_grenade_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAbilityDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "PlasmaGrenade", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


class StikkbombAbility(ActiveAbility):
    """`StikkbombAbility.ExecuteBehaviour` @18120c180 (id 1051, orksOrkBoys).

    Séquence native : `AttackWithAttackDamage(actor, target, MinMaxDamage, Blast, nrOfHits=2)` +
    `AtomicGroup(Foreach(splash = AdjacentUnits(target), team-param 3 → ennemis du caster)
    AttackWithAttackDamage(actor, s, MÊME MinMaxDamage, Blast, nrOfHits_2=1))` (l'`AtomicGroup` = no-op
    offline). Splash = `_adjacent_enemies_of`, plage PARTAGÉE. Profil Blast, ranged (range 2)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Stikkbomb)  # 1051
    ABILITY_ID = "Stikkbomb"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        splash = _adjacent_enemies_of(state, caster_id, target_id)
        return {"ability": "Stikkbomb", "caster": caster_id, "target": target_id,
                **_splash_ability_behaviour(state, caster_id, target_id, self.ABILITY_ID,
                                            "Blast", ranged=True, splash_set=splash)}


class FragstormAbility(ActiveAbility):
    """`FragstormAbility.ExecuteBehaviour` @1811e0a00 (id 1078, templSmnAggressor).

    Séquence native : `AttackWithAttackDamage(actor, target, MinMaxDamage, Blast, nrOfHits=4)` +
    `Foreach(splash = PickRandomly(AdjacentTiles(target) − tuiles alliées, nrOfTargets=4))
    AttackWithAttackDamage(actor, s, MÊME MinMaxDamage, Blast, nrOfHits_2=2)`. Splash = jusqu'à 4 ennemis
    adjacents à la cible, PICK-RANDOM (`_pick_randomly_n`), plage PARTAGÉE. ⚠ GAP : coût/ordre RNG du pick
    non calibré (désync possible de `state.rng` si >4 candidats) ; ≤4 candidats → tous, sans RNG."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Fragstorm)  # 1078
    ABILITY_ID = "Fragstorm"
    N_TARGETS = 4        # constants.nrOfTargets (borne du PickRandomly splash)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        splash = _pick_randomly_n(state, _adjacent_enemies_of(state, caster_id, target_id), self.N_TARGETS)
        return {"ability": "Fragstorm", "caster": caster_id, "target": target_id,
                **_splash_ability_behaviour(state, caster_id, target_id, self.ABILITY_ID,
                                            "Blast", ranged=True, splash_set=splash)}


class ScythingTalonsAbility(ActiveAbility):
    """`ScythingTalonsAbility.ExecuteBehaviour` @1812059f0 (id 1065, tyranSmnWarrior).

    Séquence native : `AttackWithAttackDamage(actor, target, MinMaxDamage, Bio, hits=condHits1)` +
    `Foreach(splash = AdjacentEnemies(actor) & AdjacentFriends(target) − target)
    AttackWithAttackDamage(actor, s, MÊME MinMaxDamage, Bio, hits=condHits2)`. Splash = ennemis adjacents à
    la FOIS au caster ET à la cible (`_adjacent_to_both`, réutilisé de CrushingClaws), plage PARTAGÉE. Melee (Bio).

    ⚠ HITS CONDITIONNELS (GAP) : `condHits = ConditionalAmount(HasTrait(target, trait enum 2), nrOfHits×2,
    nrOfHits)` — les hits DOUBLENT (3→6 main, 2→4 splash) si la cible a le trait enum `2` (famille du 0xd
    CrushingClaws, NON mappé offline — pas de map TRAIT dans enum_maps). On porte les hits de BASE (3/2,
    jamais de sur-compte) ; le doublement s'ajoutera une fois le trait 2 identifié (via `target` gameconfig)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ScythingTalons)  # 1065
    ABILITY_ID = "ScythingTalons"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        splash = _adjacent_to_both(state, caster_id, target_id)
        return {"ability": "ScythingTalons", "caster": caster_id, "target": target_id,
                **_splash_ability_behaviour(state, caster_id, target_id, self.ABILITY_ID,
                                            "Bio", ranged=False, splash_set=splash)}


class GravitonRifleAbility(ActiveAbility):
    """`GravitonRifleAbility.ExecuteBehaviour` @1811e31a0 (id 1206, votanIronmaster).

    Séquence native (`+` = op_Addition) :
        AttackWithAttackDamage(target, 3x Physical, +extraPierce vs Gravis/Terminator/Mechanical)  # [TODO]
      + AddEffect(0x48a Stunned, source=casterStateRef, TurnsFromRounds(GetNumberConstant 0x45 = nrOfRounds=1))
    MÊME pattern AddEffect que ThunderousAssault. ⚠ votanIronmaster N'EST PAS dans le pool du runner
    (non spawnable) → cette ability n'est PAS validée live ; portée pour documenter le pattern partagé."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GravitonRifle)  # 1206

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        atk = None
        if target_id is not None:
            # [attaque] 3x Physical (range 2). ⚠ extraPierceRatio CONDITIONNEL (+40% vs Gravis/Terminator/
            # Mechanical) NON modélisé ici (TODO : gate sur le type de cible) ; pierce de base sinon.
            bmin, bmax, pierce, hits = ability_attack_params(
                state, caster_id, "GravitonRifle", "Physical", ranged=True)
            atk = AttackDamageOperation.execute_ability_attack(
                state, caster_id, target_id, bmin, bmax, pierce, hits,
                damage_profile="Physical", is_melee=False)
            # [AddEffect] Stunned 1162, durée = TurnsFromRounds(nrOfRounds=1) :
            AddEffectOperation.execute(state, source=caster_id, target=target_id,
                                       effect_type=STUNNED, name="Stunned",
                                       duration_override=turns_from_rounds(1))
        return {"attack": atk}
