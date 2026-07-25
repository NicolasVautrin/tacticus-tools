"""Abilities Ultramarines (namespace natif `Abilities.Active.Loki.*`, faction Imperial/Ultramarines).

Module DEDIE (org faction, comme `deathguard.py`/`genestealer.py`) : l'org native est 1 classe par
ability (`Abilities.Active.Loki.<X>Ability`) ; les arbres SPECIFIQUES vivent avec leur classe. RE ghidra
gqfc5mff6c (VA citees). Case-220 §1 P0-HEAL.

Arbre `CombatRestorativesAbility.ExecuteBehaviour @1811cc590` (id 1002, ultraApothecary) — MIRROR du
DECOMPILE (+ `HealTargets @1811cca50`, callback `<ExecuteBehaviour>b__0 @1811e3e90`). JUMEAU IMPERIAL du
Chaos 1037 RevitalizingMalignancy (`deathguard.py`), mais AVEC DEUX DIFFERENCES STRUCTURELLES lues au
decompile (pas devinees par symetrie) :

    base        = Healable( op_Addition( Friends(AdjacentUnits(casterTile, 1)), caster ) )   # PAS d'exclusion trait
    withImperial = SelectUniqueUnits( UnitsWithTrait( base, 0x1a Imperial ) )    heal Get(var0x22)   # allies Imperial
    sans         = SelectUniqueUnits( op_Subtraction( base, withImperial ) )     heal Get(var0x20)   # tout le reste
    ExecuteAtomic( op_Addition( Heal(withImperial, ...) , Heal(sans, ...) ) )                 # withImperial PUIS sans

DIFFERENCE 1 -- PAS DE CUMUL. Le natif lit var0x22 (`GetVariableForLevel(0x22)` @1811cc590 -> +0x20) ET
var0x20 (`GetVariableForLevel(0x20)` -> +0x160) SEPAREMENT, SANS les sommer (contraste le jumeau 1037 ou
+0x160 = `iVar14 + iVar13`, CUMUL Chaos). Chaque groupe recoit UN montant simple :
  - allie IMPERIAL(0x1a) : var0x22 = `hpToHeal_2[level]`  (le PLUS gros, 5456 max)   [callback: 1er Heal]
  - allie NON-Imperial   : var0x20 = `hpToHeal[level]`    (4365 max)                 [callback: 2e Heal]
Les deux vars sont dans `variablesAffectedByRarityBonus` -> scalees par `AbilityVariablesMultiplier`
(mirror `ability_var(..., multiplier_pct=mult)`). Chaque `GetVariableForLevel` est lu+arrondi SEPAREMENT.

DIFFERENCE 2 -- PAS D'EXCLUSION DE TRAIT AU TOP. Le jumeau 1037 exclut Imperial du set entier
(`WithoutTrait(0x1a)`) -> les allies Imperial recoivent 0. Ici 1002 n'exclut RIEN : le set est
`Healable(Union(adjacent friends, self))` puis splitte Imperial / non-Imperial ; TOUS les allies adjacents
+ self (blesses, non-mechanical) sont soignes. `sans = op_Subtraction(base, withImperial)` == non-Imperial
membres de base (Xenos ET Chaos allies inclus, contrairement au 1037 qui excluait Imperial).

La garde `Healable` (`HealableUnitsSelector`, kind 4 du wrapper natif `FUN_180025220(4, ...)` applique a
base AVANT le split) est portee COTE MUTATION (feuille `Heal(guard=healable_heal_type_0)`, cf.
`behaviours/stats.py`) : Healable(base) puis split == split puis Healable-par-feuille (Healable idempotent,
distribue sur l'intersection/soustraction -> sets finaux identiques ; demonstration : withImperial cap
Healable = Imperial cap base cap Healable = Imperial cap Healable(base) ; sans cap Healable = idem).

Le trait Imperial(0x1a) est ABSENT de `gameconfig.unit().traits` (0 unite le porte) -> DERIVE de la
GrandAlliance (`GrandAlliance.GetTrait @1815647a0`) via `_grand_alliance_trait` (context.py), DEJA cable
dans `_unit_dict` (ajoute le trait d'alliance au set runner). REUTILISE tel quel (jumeau 1037)."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const, resolve_unit
from ...dsl.effects import ExecutionContext, AbilityBehaviour, OperationResult
from ...entities.behaviours import op_add, op_and, AtomicGroup
from ...entities.formulas import If as FormulaIf
from ...entities.selectors import (Caster, CasterTile, AdjacentUnits, FixedTileIds, Friends,
                                   TilesInTriangleShape, TilesOnSameElevation, Union,
                                   UnitsWithTrait, Sub, Unique, Target, Walkable)
from ...entities.traits.unit_trait import UnitTrait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.stats import StatType
from ...entities.triggers import IsPositionMachineForCurrentPlayer
from ..components import StatsComponent, OwnerComponent, PositionComponent
from .base import ActiveAbility, convert_rounds_to_turns
from .behaviours import (entities_from_state, AddEffect, Heal, healable_heal_type_0,
                         AttackWithAttackDamage, PushUnit)

if TYPE_CHECKING:
    from ..state import State

ABILITY_ID = "CombatRestoratives"


def _heal_amounts(state: "State", caster_id: int) -> tuple[int, int]:
    """(imperial, sans) — mirror des lectures de `ExecuteBehaviour @1811cc590` :
        var0x22 = GetVariableForLevel(config, 0x22) = `hpToHeal_2`  -> withImperial (allies Imperial)   [+0x20]
        var0x20 = GetVariableForLevel(config, 0x20) = `hpToHeal`    -> sans (non-Imperial)               [+0x160]
    AUCUNE somme (contraste 1037 ou +0x160 = iVar14 + iVar13). Chaque var est lue+arrondie SEPAREMENT via
    `ability_var` (le natif bake le scaling rarete/progression `AbilityVariablesMultiplierPercentage` dans
    la config par-unite ; les DEUX vars sont dans `variablesAffectedByRarityBonus`). ANGLE VALIDATOR : ne
    pas fitter un scalaire -- imperial et sans sont deux vars distinctes (hpToHeal_2 != hpToHeal)."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = getattr(ctx, "ability_variables_multiplier", 100) if ctx is not None else 100
    imperial = int(ability_var(ABILITY_ID, "hpToHeal_2", level, multiplier_pct=mult) or 0)  # var0x22 (Imperial)
    sans = int(ability_var(ABILITY_ID, "hpToHeal", level, multiplier_pct=mult) or 0)        # var0x20 (non-Imperial)
    return imperial, sans


def combat_restoratives_tree(imperial_amount: int, sans_amount: int) -> AtomicGroup:
    """Arbre de `CombatRestorativesAbility.ExecuteBehaviour @1811cc590` (MIRROR 1:1 du decompile + callback
    `b__0 @1811e3e90`). `base` = self + allies adjacents (hex 1), filtre `Healable` porte cote mutation
    (`Heal(guard=healable_heal_type_0)`). Split par trait Imperial(0x1a) : allies Imperial = `imperial_amount`
    (var0x22 = hpToHeal_2), tout le reste = `sans_amount` (var0x20 = hpToHeal). `withImperial` /`sans` sont
    chacun wrappes `SelectUniqueUnits` (dedup natif, no-op sur des sets deja uniques -> mirror fidele).
    `sans = op_Subtraction(base, withImperial)` = membres non-Imperial de base. `AtomicGroup` (`ExecuteAtomic`,
    id 0x1f). Ordre callback natif : Heal(withImperial) PUIS Heal(sans) ; feuilles pures (aucun rng) + sets
    DISJOINTS -> ordre sans effet observable (fidelite conservee)."""
    base = Union(Friends(AdjacentUnits(CasterTile(), Const(1))), Caster())    # op_Addition(Friends(AdjacentUnits(casterTile,1)), caster)
    with_imperial = Unique(UnitsWithTrait(base, int(UnitTrait.Imperial)))     # SelectUniqueUnits(UnitsWithTrait(base, 0x1a))
    sans = Unique(Sub(base, with_imperial))                                   # SelectUniqueUnits(op_Subtraction(base, withImperial))
    heal_imperial = Heal(with_imperial, lambda entities, ectx: imperial_amount,
                         guard=healable_heal_type_0)                          # Get(var0x22) = hpToHeal_2
    heal_sans = Heal(sans, lambda entities, ectx: sans_amount,
                     guard=healable_heal_type_0)                              # Get(var0x20) = hpToHeal
    return AtomicGroup(op_add(heal_imperial, heal_sans))                      # ExecuteAtomic( withImperial + sans )


class CombatRestorativesAbility(ActiveAbility):
    """`CombatRestorativesAbility.ExecuteBehaviour @1811cc590` (id 1002, ultraApothecary — Ultramarines).

    Heal-splitte-par-trait (jumeau IMPERIAL de 1037 RevitalizingMalignancy) : soigne le caster + ses allies
    adjacents (hex 1). Le montant depend du trait Imperial de la cible :
      - allie IMPERIAL(0x1a) : `hpToHeal_2[level]`  (var0x22)
      - allie NON-Imperial   : `hpToHeal[level]`    (var0x20)
    PAS de cumul (contraste 1037) ; PAS d'exclusion de trait (tous les allies adjacents + self, blesses +
    non-mechanical, sont soignes). Garde `Healable` (HP<max ET non-mechanical) portee cote mutation (feuille
    `Heal(guard=...)`). Behaviour = arbre DSL `combat_restoratives_tree` (mirror 1:1 du decompile + callback
    `b__0 @1811e3e90`). Deterministe (aucun rng)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CombatRestoratives)  # 1002
    ABILITY_ID = ABILITY_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # Montants lus AU CAST (mirror : le natif lit var0x22/var0x20 dans ExecuteBehaviour et les fige dans
        # le closure de l'AtomicGroup) ; l'arbre cible Caster() (pas Target()) -> target_id indifferent.
        imperial_amount, sans_amount = _heal_amounts(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        combat_restoratives_tree(imperial_amount, sans_amount).execute(entities, ectx)
        heals = [p for n, p in ectx.emitted if n == "Heal"]
        return {"ability": ABILITY_ID, "caster": caster_id, "target": target_id,
                "imperial_amount": imperial_amount, "sans_amount": sans_amount,
                "heals": heals, "dsl": True}


MORTIS_ROUND_ID = "MortisRound"


def mortis_round_tree() -> AtomicGroup:
    """Arbre de `MortisRoundAbility.ExecuteBehaviour @1811f54a0` (id 1004, ultraEliminatorSgt — MIRROR du
    DECOMPILE + callback `<ExecuteBehaviour>b__0 @1811fd290`) :
        AtomicGroup( 0x3f, [callback b__0 = ] Execute(attack) PUIS Execute(push) )
      attack = AttackWithAttackDamage(caster@factory+0x160, target@factory+0x178, MinMaxDamage(minDmg 0xc/
               maxDmg 0xd), GetDamageProfile=HeavyRound, hitsNode@factory+0xc0, AbilityOrEffect(*this+0x10
               =1004))                                          # 1x HeavyRound ranged (i2 « 1x 3274-3638 »)
      push   = PushUnit(factory, caster@factory+0x160, target@factory+0x178, 0)   # recul 1 hex (i2)

    Structure = SOUS-ENSEMBLE de ThunderousAssault (`strike.py`) : attaque MONO-cible + push, SANS stun/
    kill-dead/charge. Le natif enroule l'attaque et le push dans un `AtomicGroup(0x3f, callback)` : le
    callback `b__0` execute `AActiveAbility.Execute(attack_node)` PUIS `AActiveAbility.Execute(push_node)`
    (ordre attaque-AVANT-push lu au decompile). Port : `AtomicGroup(op_and(Attack, Push))` — `op_and` =
    `CombinedBehaviour` (Seq gauche->droite, effets PURS) == l'ordre du callback ; `AtomicGroup` = inline
    pass-through (RE #201). `PushUnit` est DETERMINISTE (aucun tirage rng) -> ne decale PAS l'ordre RNG de
    l'attaque : bit-exact BY CONSTRUCTION vs un imperatif attaque->push.

    Overload d'attaque : le call-site @1811f5683 appelle `DSLFactory.AttackWithAttackDamage @180dea520`
    (famille ATTACK, resolu par XREF — PAS le nom ; @180dea520 != le @180de9fb0 de ThunderousAssault, mais
    MEME famille attack, precedents portes ScythingTalons/Executioner) -> `native_factory="attack"` (defaut,
    resolve slot-8 gaspille = 2 tirages/coup a cc=0). Profil `HeavyRound` (constants.damageProfile), attaque
    RANGED (attackRangeType=Ranged, range 3) -> `is_melee=False`. `nrOfHits` ABSENT de la config (constants
    n'a que damageProfile) -> `ability_attack_params` rend hits=1 (== i2 « 1x »). `ability_type=1004` threade
    l'AbilityOrEffect du coup (mirror `op_Implicit(*this+0x10)` natif = 7e arg de AttackWithAttackDamage) —
    c'est le VEHICULE du gate `TriggeringAbilityIs(0x3ec=1004)` du bonus HeavyWeapon_ExtraDmg (#47 :
    `execute_ability_attack` threade DESORMAIS is_ranged + trigger_ability_type -> +50% valide bit-exact)."""
    attack = AttackWithAttackDamage(Target(), MORTIS_ROUND_ID, "HeavyRound", is_melee=False,
                                    ability_type=int(ActiveAbilityType.MortisRound))
    push = PushUnit(Caster(), Target())
    return AtomicGroup(op_and(attack, push))


class MortisRoundAbility(ActiveAbility):
    """`MortisRoundAbility.ExecuteBehaviour @1811f54a0` (id 1004, ultraEliminatorSgt « Eliminator Sergeant »,
    Ultramarines — namespace natif `Abilities.Active.Loki.MortisRoundAbility`). MIRROR du DECOMPILE, arbre DSL
    (`mortis_round_tree`) :
        AtomicGroup( Attack(HeavyRound, 1x, caster->target) PUIS PushUnit(caster, target) )

    i2 : « Deals 1x 3274-3638 Heavy Round Damage to a single target within range 3, which is then pushed back
    1 hex. The Heavy Weapon trait applies double to this ability. » Le behaviour = attaque MONO-cible HeavyRound
    (1 coup) + recul 1 hex de la cible (`DisplaceUnitOperation`, no-op si BigTarget/Immovable/bord). SOUS-ENSEMBLE
    structurel de ThunderousAssault (attaque + push, sans stun/charge).

    QUIRK « Heavy Weapon applies double » (i2) — RESOLU #47 (2026-07-24) : n'est PAS dans
    l'ExecuteBehaviour. C'est un raffinement de l'effet `HeavyWeapon_ExtraDmgEffect.CreateDamageModifier
    @180f4f030` (accorde par le trait HeavyWeapon du carrier ; effet 1008 SEEDE dans le runner) :
    `amount = ConditionalAmount(TriggeringAbilityIs(0x3ec=1004) ? Multiply(base, Direct(2)) : base)`
    ou `base = ConfigConst 0xf = heavyWeaponExtraDmg` (=25). => le bonus +extraDmg% des attaques RANGED du
    porteur (gate `OwnerIsCaster & IsRangedAttack & no-move`) est DOUBLE (+50% au lieu de +25%) quand l'attaque
    declenchante est MortisRound. #47 : `execute_ability_attack` threade `is_ranged` + `trigger_ability_type`
    dans la collecte attacker-modifiers (gate famille ATTACK, cf. damage.py) -> le x2 s'applique via
    `att_ctx["trigger_ability_type"]` lu par `HeavyWeaponExtraDmgEffect`. L'ancien ratio live ~3.15x etait
    DEUX etages : x1.5 (HeavyWeapon double) + KNOCKBACK de collision du push BLOQUE au bord
    (`ApplyKnockbackTo @180e67fc0` = ceil(maxHealth x 20%) = BC.Damage.KnockbackPercentage, porte dans
    displace.py) — PAS un crit-rng desync (refute par comptage mti : 2 tirages/cast = valeur + resolve,
    AUCUN crit-roll). Le pct=20 (et non 10) est prouve par mesure ISOLEE #61 : sur necroWarden le net
    hpDelta etait confondu par LivingMetalRepair (heal 10% du maxHealth) ; l'event knockback separe =
    ceil(maxHealth x 20%) (30001 -> 6001 ; 50000 -> 10000).

    Push DETERMINISTE (aucun rng) -> n'altere PAS l'ordre RNG de l'attaque : la SEQUENCE attaque->push est
    fidele BY CONSTRUCTION (l'attaque delegue au pipeline partage `execute_ability_attack`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MortisRound)  # 1004
    ABILITY_ID = MORTIS_ROUND_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        mortis_round_tree().execute(entities, ectx)
        atk = next((p.get("attack") for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        push = next((p for n, p in ectx.emitted if n == "PushUnit"), None)
        return {"ability": MORTIS_ROUND_ID, "caster": caster_id, "target": target_id,
                "main_attack": atk, "push": push, "dsl": True}


DEATH_FROM_ABOVE_ID = "DeathFromAbove"


def _dfa_spawn_tiles(state: "State", caster_id: int, target_id: int) -> list:
    """`AdjacentTiles(Target@0x178)` -> `CanAddUnit` -> `SortByDistance(caster@0x160)` (@1811d1b20 /
    `GetPossibleSpawnTiles @1811d2160`) : tuiles LIBRES (marchables, non occupees) adjacentes a la CIBLE,
    triees ASCENDANT par distance-hex au CASTER. `SortByDistanceSelector.Select @180ef2ce0` = `Enumerable.
    OrderBy` (.NET, STABLE) sur la cle `PositionComponent.Distance(caster, tile)` (lambda @180efd0e0) -> la
    plus proche du caster d'abord. DETERMINISTE (0 tirage rng, contraste `_pick_randomly`).

    ADJACENCE = `_free_tiles_adjacent` -> `board.neighbours(target)`. Le natif `AdjacentTiles`/`CanAddUnit`
    (`TileExtensions.CanAddUnit @180ec4c60` + le graphe d'adjacence du board) porte une PORTE D'ELEVATION :
    une tuile hex-voisine de la cible n'est ADJACENTE que si |elev(tuile) - elev(cible)| < 2 (verifie live :
    le champ `neighbours` du boardGraph exclut une voisine geometrique a dElev>=2 -- ex. MC1_67 tuile Swamp
    elev4 voisine d'une cible elev2). Cette porte est DEJA BAKEE dans `Board(adjacency="native_sym")`
    (= le champ `neighbours` du boardGraph, le mode CANONIQUE de production, scene.py:412) -> `board.neighbours`
    la respecte. En mode `evenq` (geometrique, sans porte) `_free_tiles_adjacent` SUR-INCLURAIT les voisines
    a dElev>=2 (== toutes les feuilles summon partagees `_free_tiles_adjacent` : convention native_sym).

    Tie-break = id de tuile (raffinement positionnel : au TIE de distance-caster, l'ordre AdjacentTiles natif
    differe, mais tous les Inceptors sont IDENTIQUES et atterrissent adjacents a la cible -> positions
    seulement ; le count et le degat total sont inchanges -- confirme bit-exact live, cf. classe DeathFromAbove)."""
    import hexgeo
    from ..operations.spawn import _free_tiles_adjacent
    board = state.board
    cas = state.get_entity(caster_id)
    cp = cas.get_component(PositionComponent) if cas is not None else None
    if board is None or cp is None:
        return []
    cands = _free_tiles_adjacent(state, target_id, set())     # CanAddUnit(AdjacentTiles(target))
    cpos = (cp.col, cp.row)

    def _key(t):
        ti = board.by_id.get(t) or {}
        return (hexgeo.distance(cpos, (ti.get("col"), ti.get("row"))), t)

    return sorted(cands, key=_key)


class SpawnInceptors(AbilityBehaviour):
    """Feuille `Spawn` de `DeathFromAboveAbility.ExecuteBehaviour @1811d1b20` (MIRROR 1:1 du DECOMPILE) :
        Spawn( caster@0x160,
               tileSel = Cache( First( SortByDistance( CanAddUnit(AdjacentTiles(Target@0x178)),
                                                       caster@0x160 ),
                                       StatAmount(caster@0x160, 0xc = TURNS_STARTED) ) ),
               unitId = GetStringConstant(config, 8) = constants["unitToSpawn"] = "ultraSmnInceptor",
               SpawnUnitOptions.WithStatsFromConfig(config 1003)
                 .onAppearance(+0x18) = UseNormalAttackIfAble(Spawned@0x180, Target@0x178) )
    UN SEUL noeud `Spawn` (plain `AActiveAbility.Execute`, PAS `ExecuteAtomic`, PAS d'AddEffect au +0x10 --
    contraste ScarabHive qui pose l'effet persistant 0x4a3). Le count est DYNAMIQUE (`GetNumSummons
    @1811d2110` = `StatAmount(caster, 0xc)` = stat 12 TURNS_STARTED du caster ; i2 « Summons 1 Inceptor for
    each round that has started ») et `First(count)` CAPPE le nombre de tuiles a min(count, tuiles libres)
    -- i2 « if not enough hexes around the target are free, fewer Inceptors will be summoned ».

    Port : placement DETERMINISTE `_dfa_spawn_tiles[:count]` (SortByDistance -> 0 rng, contraste
    `SpawnUnitOperation.execute` qui consommerait du rng via `_pick_randomly` -> desyncerait les attaques
    on-appearance) ; le SPAWN par tuile delegue a `_spawn_config_grot` (== la creation per-summon de
    `SpawnUnitOperation.execute` : owner CopyOwner team+player du caster, stats `ability_var(DeathFromAbove,
    summonHp/summonDmg/summonArmor, casterLevel, mult)`, owner-effects traits + abilities derivees). Puis
    l'ON-APPEARANCE `UseNormalAttackIfAble(Target)` = `_summon_on_appearance_attack(summon, target, None)`
    (aucun `unitDamageProfile` override -> attaque NORMALE de l'Inceptor : Bolter 6 coups, pierce 20, base =
    stat Attack du summon). ORDRE des attaques = ordre de spawn (tuile la plus proche du caster d'abord) ;
    comme tous les Inceptors sont IDENTIQUES, le TOTAL de degat a la cible est INDEPENDANT de l'ordre
    (bit-exact BY CONSTRUCTION). Emet 'SpawnUnit'/'SummonOnAppearance'. Effet PUR."""
    __slots__ = ("target_ref",)

    def __init__(self, target_ref):
        self.target_ref = target_ref

    def execute(self, entities, ectx):
        import gameconfig as GC
        from ..operations.spawn import _spawn_config_grot
        from .loki import _summon_on_appearance_attack
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        tu = resolve_unit(self.target_ref, entities)          # Target@0x178
        target_id = tu.get("id") if tu else None
        if state is None or caster_id is None or target_id is None:
            return OperationResult.ok()
        vid = ((GC.ability(DEATH_FROM_ABOVE_ID) or {}).get("constants") or {}).get("unitToSpawn")
        if vid is None:                                       # GetStringConstant(config, 8)
            return OperationResult.ok()
        ce = state.get_entity(caster_id)
        coc = ce.get_component(OwnerComponent) if ce is not None else None
        csc = ce.get_component(StatsComponent) if ce is not None else None
        c_ctx = csc.ctx if csc is not None else None
        if coc is None or c_ctx is None:
            return OperationResult.ok()
        level = getattr(c_ctx, "active_ability_level", None)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        # count = StatAmount(caster, 0xc = TURNS_STARTED) [GetNumSummons @1811d2110] ; AUCUN plancher
        # (StartTurn incremente AVANT le cast -> >=1 pendant le tour du caster ; raw fidele au natif).
        count = int(c_ctx.stat(StatType.TURNS_STARTED) or 0)
        # First(count) CAPPE naturellement au nombre de tuiles libres (i2 « fewer Inceptors »).
        tiles = _dfa_spawn_tiles(state, caster_id, target_id)[:max(0, count)]
        spawned: list = []
        for tile in tiles:
            gid = _spawn_config_grot(state, vid, tile, DEATH_FROM_ABOVE_ID, level, mult,
                                     coc.team, coc.player)
            if gid is not None:
                spawned.append(gid)
                ectx.emit("SpawnUnit", tile=tile, unit=gid)
        # on-appearance : chaque Inceptor attaque la CIBLE (attaque normale Bolter ; profil None -> arme).
        for gid in spawned:
            res = _summon_on_appearance_attack(state, gid, target_id, None)
            if res is not None:
                ectx.emit("SummonOnAppearance", summon=gid, total=res.get("total"))
        return OperationResult.ok()


def death_from_above_tree() -> "SpawnInceptors":
    """Arbre de `DeathFromAboveAbility.ExecuteBehaviour @1811d1b20` = UN noeud `Spawn` unique (feuille
    `SpawnInceptors`). Cf. sa docstring pour le mirror complet du decompile."""
    return SpawnInceptors(Target())


class DeathFromAboveAbility(ActiveAbility):
    """`DeathFromAboveAbility.ExecuteBehaviour @1811d1b20` (id 1003, ultraInceptorSgt « Inceptor Sergeant »,
    Ultramarines -- namespace natif `Abilities.Active.Loki.DeathFromAboveAbility`). MIRROR du DECOMPILE,
    arbre DSL (`death_from_above_tree`) : spawn N Inceptors (`ultraSmnInceptor`) sur des tuiles libres
    adjacentes a la cible (triees par distance-caster), chacun attaquant la cible immediatement.

    i2 : « Summons 1 Inceptor for each round that has started. The Inceptors land adjacent to the target,
    whom they attack immediately. Note: if not enough hexes around the target are free, fewer Inceptors
    will be summoned. » -> count = `GetNumSummons @1811d2110` = `StatAmount(caster, 0xc = TURNS_STARTED)`
    (stat 12, per-unit `UnitComponent.turnsStarted@+0x58` bumpe par StartTurn), CAPPE par `First(count)` au
    nombre de tuiles libres. Placement = `SortByDistance(caster)` DETERMINISTE (0 rng). Stats des Inceptors
    = `WithStatsFromConfig(DeathFromAbove)` = `ability_var(summonHp/summonDmg/summonArmor, casterLevel,
    mult)`. On-appearance = `UseNormalAttackIfAble(Target)` = attaque normale (Bolter 6 coups, PAS de profil
    override -- contraste ScarabHive Piercing). PAS d'effet persistant pose (contraste ScarabHive 0x4a3).

    NB (residu inerte) : l'`AbilityOrEffect(1003)` que le natif threade dans `UseNormalAttackIfAble`
    (`op_Implicit(*this+0x10)`, meme vehicule que MortisRound) n'a AUCUN consommateur porte -> non threade
    (l'on-appearance reste une attaque normale). Le placement subset au tie (SortByDistance stable) est un
    raffinement POSITIONNEL : count et degat total identiques (Inceptors identiques, tous adjacents cible).
    ShockAssault (passif du carrier, On(0xa)) est un item DISTINCT (case-220 §6.9 [opus]+prerequis) : PAS
    porte ici -- l'on-appearance est la seule attaque de ce cast.

    Flags de tour : defauts base (`SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag` = True) -> termine le tour
    du caster + pose ActiveAbilityUsed.

    VALIDE LIVE (agreement, board MC1_67 native_sym elevation-gated, cible tyranTyrantGuard hp force) --
    BIT-EXACT count ET degat total on-appearance : TURNS_STARTED=1 -> 1 Inceptor (8759), =2 -> 2 (11764),
    =3 -> 3 (11460) ; CAP tuiles TURNS_STARTED=4 free=3 -> 3 (11460) et =6 free=3 -> 3 (12084, seed 31337).
    Le degat inclut le bonus d'ELEVATION (#45, threade dans `execute_normal_like`). Placement deterministe
    (0 rng) -> ordre des attaques sans effet sur le total (Inceptors identiques)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DeathFromAbove)  # 1003
    ABILITY_ID = DEATH_FROM_ABOVE_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        death_from_above_tree().execute(entities, ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "SummonOnAppearance"]
        return {"ability": DEATH_FROM_ABOVE_ID, "caster": caster_id, "target": target_id,
                "spawned": spawned, "attacks": attacks, "dsl": True}


# =================================================================================================== #
# MacroPlasmaIncinerator (1159, `ultraDreadnought` -- Redemptor Dreadnought, MachineOfWar) -- #90-B
# Patron « pose d'effet(s) seule » : le CAST ne fait que MARQUER une zone de 3 hexes et ARMER la MoW ;
# le degat vient de la phase 2 (effet `MacroPlasmaIncinerator_AutoAttack` porte par la MoW), NON portee.
# =================================================================================================== #

MACRO_PLASMA_ID = "MacroPlasmaIncinerator"
MACRO_PLASMA_TILE = int(EffectType.MacroPlasmaIncinerator_Tile)               # 0x537 = 1335
MACRO_PLASMA_AUTO_ATTACK = int(EffectType.MacroPlasmaIncinerator_AutoAttack)  # 0x538 = 1336
# `MachineOfWarPosition.Bottom` = 2, la valeur litterale passee a
# `DSLFactory.IsPositionMachineForCurrentPlayer(2)` @1811f1910.
MACHINE_POSITION_BOTTOM = 2


def macro_plasma_incinerator_tree(target_tile_id: int, duration_turns: int):
    """Arbre de `MacroPlasmaIncineratorAbility.ExecuteBehaviour @1811f1910` -- MIRROR 1:1 du DECOMPILE :

        dir   = If( IsPositionMachineForCurrentPlayer(2), Direct(1), Direct(4) )
        tiles = Walkable( TilesOnSameElevation( target@0x178,
                            TilesInTriangleShape(target@0x178, dir), 1 ) )
        Execute(   AddEffect(0x537=1335 MacroPlasmaIncinerator_Tile, absRef, source=owner@0x148,
                             targets=tiles, TurnsFromRounds(1))
                 & AddEffect(0x538=1336 MacroPlasmaIncinerator_AutoAttack, absRef,
                             targets=owner@0x148, TurnsFromRounds(1)) )

    (`AActiveAbility.Execute`, PAS `ExecuteAtomic`.) La 2e `AddEffect` utilise la surcharge SANS
    argument `source` (6 args au lieu de 7) -> l'effet se pose sur l'OWNER = la MoW elle-meme.

    GEOMETRIE. `TilesInTriangleShape` = la tuile ciblee + les DEUX voisines du coin `dir`
    (`BattleQuery.GetTilesInTriangleShape @18106ba60`) : `dir=1` -> {S, SE}, `dir=4` -> {NW, N}. Le coin
    depend du COTE du plateau ou se deploie la MoW du joueur COURANT (slot Top/Bottom) -- le
    Dreadnought bombarde « vers l'avant ». Puis filtre elevation (ecart <= 1 vs la tuile ciblee) et
    walkable. Bords de plateau : les voisines hors-plateau sont simplement absentes.

    DUREE. `TurnsFromRounds(1)` -> `BattleQuery.ConvertRoundsToTurns @181058af0` = `count(joueurs
    non-Environment) x 1` = **2** dans nos runners (MESURE : `remaining = 2` live sur les deux effets)
    -> passee en `duration_turns` (deja convertie par la classe d'ability via `convert_rounds_to_turns`)."""
    tgt = FixedTileIds([target_tile_id])
    direction = FormulaIf(IsPositionMachineForCurrentPlayer(MACHINE_POSITION_BOTTOM),
                          Const(1), Const(4))
    tiles = Walkable(TilesOnSameElevation(tgt, TilesInTriangleShape(tgt, direction), 1))
    return op_and(
        AddEffect(MACRO_PLASMA_TILE, EffectType.MacroPlasmaIncinerator_Tile.name, tiles,
                  duration_rounds=None, duration_turns=duration_turns),
        AddEffect(MACRO_PLASMA_AUTO_ATTACK, EffectType.MacroPlasmaIncinerator_AutoAttack.name,
                  Caster(), duration_rounds=None, duration_turns=duration_turns))


class MacroPlasmaIncineratorAbility(ActiveAbility):
    """`MacroPlasmaIncineratorAbility.ExecuteBehaviour @1811f1910` (id 1159, `ultraDreadnought` --
    Redemptor Dreadnought, Ultramarines, MachineOfWar). Cast TILE-TARGET (`abilityTargets` kind="tile").

    RE (ghidra gqfc5mff6c) :
    - `ExecuteBehaviour @1811f1910` : cf. `macro_plasma_incinerator_tree` (2 `AddEffect`, zero attaque).
    - `.ctor @1811f1c80` ; `GetTargetAreaTiles @1811f1b90` = la MEME chaine de tuiles, exposee pour la
      PREVIEW / le playbook (`Loki.MacroPlasmaIncineratorPlaybook`), pas pour l'execution.
    - PHASE 2 (NON PORTEE) : l'effet `MacroPlasmaIncinerator_AutoAttack` (1336) pose SUR la MoW declenche
      le tir sur les tuiles marquees `MacroPlasmaIncinerator_Tile` (1335) -- c'est la qu'interviennent
      `minDmg`/`maxDmg`, `damageProfile=Plasma`, `nrOfHits=3`.

    OBSERVABLE DU CAST (mesure live, runner MoW C1_02 slot 2, caster 53, cible = tuile (0,0) au COIN du
    plateau 5x7) : tuiles (0,0) (0,1) (1,1) + `MacroPlasmaIncinerator_Tile` (1335, source 53, remaining 2)
    ; mow53 + `MacroPlasmaIncinerator_AutoAttack` (1336, remaining 2). `dir=1` (= {S, SE}) confirme que
    `IsPositionMachineForCurrentPlayer(2)` est VRAI pour une MoW de slot 2 du joueur courant.

    `target_id` = id de TUILE (cast tile-target). Un `target_id` qui n'est pas une tuile du board -> no-op.
    Flags de tour : defauts base (1159 hors tables d'override) -> termine le tour + ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MacroPlasmaIncinerator)   # 1159
    ABILITY_ID = MACRO_PLASMA_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        if tile_id is None:
            return {"tile": None, "posed": [], "dsl": True}
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id)
        turns = convert_rounds_to_turns(state, 1)          # TurnsFromRounds(1)
        macro_plasma_incinerator_tree(tile_id, turns).execute(entities, ectx)
        posed = [{"target": p["target"], "effect": p["effect_type"]}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"tile": tile_id, "turns": turns, "posed": posed, "dsl": True}
