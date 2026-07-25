"""Abilities BlackLegion (namespace natif `Abilities.Active.Loki.*`) — case-220 §6.11.

Module DEDIE a la faction Black Legion (comme `genestealer.py`/`deathguard.py` : une classe par ability,
l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (VA citees). Doc : docs/rl/case-220/black-legion.md.

Contenu :
- `BringerOfDespair` (1022, Angrax `blackTerminator`) — attaque MAIN 4x Power sur la cible + bonus 4x Power
  sur UN ennemi aleatoire adjacent au CASTER (template splash `loki/splash.py`, factory attack).
- `Incursion` (1021, Vitruvius `blackPossession`) — `ChainBehaviour` de spawns Bloodletter adjacents a la
  cible + on-appearance `UseNormalAttackIfAble` (case-220 P0-SUMMON).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import AtomicGroup, ChainBehaviour, op_and
from ...entities.selectors import (ActiveTarget, AdjacentTiles, AdjacentUnits, CanAddUnit, Caster,
                                   CasterTile, Damageable, Enemies, FixedTileIds, Friends, Nothing,
                                   Null, Sub, Target)
from ...entities.triggers import IsAlive, IsInRange, TriggerAnd
from ...entities.active_ability_type import ActiveAbilityType
from .base import ActiveAbility
from .behaviours import entities_from_state, AttackWithAttackDamage, Spawn, UseActiveAbility

if TYPE_CHECKING:
    from ..state import State


def bringer_of_despair_tree() -> AtomicGroup:
    """Arbre de `BringerOfDespairAbility$$ExecuteBehaviour @1811be740` (id 1022, Angrax `blackTerminator` —
    MIRROR du DECOMPILE + `GetValidBonusTargets @1811bebc0` / `GetHitsToBonusTarget @180fb1690` /
    `GetDamageProfile @1811beb50`) :

        bonusSel = PickRandomly(                                                          # @1811be740
                     Damageable( Enemies( caster@0x148, AdjacentUnits(casterTile@0x168, radius=1) ) )
                     op_Subtraction Target()@0x178,
                     nrOfTargets = 1 )
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage, GetDamageProfile=Power,
                                    hits = GetNumberConstant(0x2f)=nrOfHits),               # [MAIN]
            AttackWithAttackDamage(caster@0x160, bonusSel,     MinMaxDamage, Power,
                                    hits = GetNumberConstant(0x32)=nrOfHits_2) ), 0x45 )     # [BONUS]

    - **Deux volets, MEME plage `MinMaxDamage`** : le decompile calcule `local_1f8 = MinMaxDamage(target)`
      UNE fois et le PARTAGE (`uVar7 = local_1f8`) entre les deux `AttackWithAttackDamage` (BringerOfDespair
      n'a AUCUN override `GetAttackDamage` -> MinMaxDamage = bornes config `minDmg`/`maxDmg` brutes,
      INDEPENDANTES de la cible). Seule la constante de coups differe : main = `nrOfHits`(0x2f), bonus =
      `nrOfHits_2`(0x32) — config 1022 : les DEUX valent 4 (i2 « 4x ... and 4x ... »). Profil `Power` (melee,
      PiercingRatio 40) pour les deux. `attackRangeType=Melee` -> `is_melee=True`.
    - **BONUS = ennemi adjacent au CASTER, PAS a la cible** : `AdjacentUnits(casterTile@0x168, radius=1)` —
      @0x168 = CasterTile (ANCRE : `GauntletsOfUltramar.GetAdjacentTargetsSelector @1811e2010` decompile
      `AdjacentTiles(@0x168)` = casterTile). `Enemies(caster@0x148, ...)` filtre a l'equipe adverse (@0x148 =
      Caster, meme role enemies-ref que @0x160 dans Gauntlets/CrushingClaws ; HeroicFusillade `caster@0x148`
      valide live). `Damageable` = vivants ciblables (PV>0). `op_Subtraction Target()@0x178` retire la cible
      MAIN (« ANOTHER random enemy »). i2 : « 4x ... to another random enemy adjacent to Angrax [le caster] ».
    - **PickRandomly(<set>, nrOfTargets=1)** FOLDE dans la feuille bonus via `pick_n=1` (== Fragstorm :
      `multi=True` folde l'`OrderBy` par id, `pick_n` folde le PickRandomly DANS la resolution du selecteur,
      `state.rng`). Evalue A L'EXECUTION du volet bonus = APRES les coups MAIN (op_BitwiseAnd = main puis bonus)
      -> l'ordre de conso `state.rng` (8 tirages main a cc=0, puis le pick, puis 8 tirages bonus) mirror le natif.
    - **native_factory = "attack"** (defaut, 2 tirages/coup a cc=0) : les DEUX volets appellent
      `DSLFactory.AttackWithAttackDamage @180de9fb0` (VERIFIE par les CALLEES de @1811be740, PAS au nom du
      commentaire — cf. rngcrit-1202/tip #2), famille attack, JAMAIS `AttackWithAbilityDamage @180de9c90`.

    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; tag 0x45 = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf.
    #209). Ordre = main PUIS bonus, cibles triees par id (OrderBy natif), meme `state.rng` -> bit-exact BY
    CONSTRUCTION (memes bornes/hits/profil que l'attaque generique). Le « Battle Fatigue triggered twice »
    de l'i2 est ABSENT de l'ExecuteBehaviour (aucun noeud effet) -> no-op degat (mecanique de trigger separee,
    hors face COMBAT).

    ⚠ GAP #215 (RNG-exact PickRandomly) : l'ordre/cout exact du tirage `PickRandomlySelector.Select` n'est pas
    cale ; `pick_n` tire des OCCUPANTS (jamais de tuile vide, CONTRASTE Fragstorm qui tire des HEXES) -> quand
    >1 ennemi damageable adjacent au caster, l'ennemi touche ET la conso `state.rng` peuvent differer. Structure
    fidele (ennemis-du-caster adjacents, cap 1, exclusion de la cible) ; RNG-exact du pick = raffinement flagge.
    len(pool)<=1 -> `_pick_randomly_n` ne roll PAS (le cas 1v1 : 0 tirage de pick, bonus vide ou unique)."""
    tgt = Target()
    main = AttackWithAttackDamage(tgt, "BringerOfDespair", "Power", is_melee=True)      # MinMaxDamage/Power/0x2f=4
    bonus_sel = Sub(Damageable(Enemies(AdjacentUnits(CasterTile(), Const(1)))), Target())  # adjacents-caster (ennemis, PV>0) − cible
    bonus = AttackWithAttackDamage(bonus_sel, "BringerOfDespair", "Power", is_melee=True,
                                   hits_key="nrOfHits_2", multi=True, pick_n=1)          # MEME plage, PickRandomly(1), 0x32=4
    return AtomicGroup(op_and(main, bonus))


class BringerOfDespairAbility(ActiveAbility):
    """`BringerOfDespairAbility$$ExecuteBehaviour @1811be740` (id 1022, Angrax `blackTerminator`, namespace
    natif `Abilities.Active.Loki`).

    Arbre DSL `bringer_of_despair_tree()` = template splash `loki/splash.py` (MEME plage main/bonus, seuls les
    coups different) mais BONUS ANCRE SUR LE CASTER (pas la cible) : (1) 4x Power sur la cible melee ; (2) 4x
    Power sur UN ennemi damageable aleatoire adjacent au caster, excluant la cible (`PickRandomly(1)` folde via
    `pick_n=1`). Profil Power (melee). Selecteurs (CasterTile/Enemies/Damageable/Sub) portes, structure
    DSL (op_BitwiseAnd, ExecuteAtomic). Renvoie {main_attack, bonus, dsl}.

    Les deux volets = `AttackWithAttackDamage(multi/mono)` -> memes Operations (`AttackDamageOperation.
    execute_ability_attack`, `native_factory="attack"` = 2 tirages/coup a cc=0) que l'attaque generique ->
    bit-exact BY CONSTRUCTION. Termine le tour (1022 hors des frozensets base.py -> flags par defaut)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BringerOfDespair)  # 1022
    ABILITY_ID = "BringerOfDespair"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # behaviour = arbre DSL (main mono-cible + bonus multi=True/pick_n=1 ancre caster) ; emet les MEMES
        # Operations (execute_ability_attack) -> meme mutation, diag main/bonus par cible.
        ectx = ExecutionContext(state=state, rng=state.rng)
        bringer_of_despair_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        bonus = [{"target": p["target"], "attack": p["attack"]}
                 for p in atks if p.get("target") != target_id]     # cibles bonus != cible principale
        return {"ability": "BringerOfDespair", "caster": caster_id, "target": target_id,
                "main_attack": main, "bonus": bonus, "dsl": True}


# ================== Incursion (blackPossession `Vitruvius`, actif 1021) -- case-220 P0-SUMMON ==================
#
# `IncursionAbility.ExecuteBehaviour @1811e9fe0` (MIRROR du DECOMPILE) :
#     unitId   = GetStringConstant(config, 0)                                    # blackSmnBloodletter
#     tgtUnit  = TargetsSelector.SelectUnit(target@0x178, entities, 3)           # cible resolue EAGER
#     opts     = SpawnUnitOptions.WithStatsFromConfig(config, level)
#     opts.+0x18 = UseNormalAttackIfAble(activeTarget@0x180, Entity(tgtUnit), <AbilityOrEffect>, ...)
#     spawnB   = Spawn(caster@0x160, activeTarget@0x180, unitId, opts)
#     chain    = ChainBehaviour(Null(), Func(this.GetNextSpawnTile), Direct(GetNumberConstant(0x3c)),
#                               spawnB, UnitTimelines.TypeToTimeline())
#     AActiveAbility.Execute(this, chain, entities)
# UN SEUL `Execute` top-level. AUCUN `PerformAIAction` : l'on-appearance est une attaque NORMALE dirigee.
CONST_INCURSION_UNIT_ID = 0x00      # GetStringConstant(0)    -> "unitId"      = blackSmnBloodletter
CONST_INCURSION_RANGE = 0x16        # GetNumberConstant(0x16) -> "range"       = 2  (MEME index que 1028)
CONST_INCURSION_MAX_SUMMONS = 0x3c  # GetNumberConstant(0x3c) -> "maxSummons"  = 6


def incursion_next_spawn_tile(state: "State", entities):
    """`IncursionAbility.GetNextSpawnTile @1811ea520` -- MIRROR ; RE-CONSTRUIT a CHAQUE ITERATION de la
    chaine (le natif passe un `System.Func<>` sur cette methode, donc une NOUVELLE instance de selecteur
    par tour -> aucune memoisation, l'etat LIVE est relu) :

        cond   = ( IsAlive(caster@0x160) op_BitwiseAnd IsAlive(target@0x178) )
                 op_BitwiseAnd IsInRange(caster@0x160, target@0x178, Direct(GetNumberConstant(0x16)))
        tiles  = CanAddUnit(AdjacentTiles(target@0x178))
        amount = ConditionalAmount(cond, 1@dsl+0xc0, 0@dsl+0xb8)
        return PickRandomly(tiles, amount, 0, 0x7fffffff, false)

    `cond` est EXACTEMENT `IncursionAbility.GetContinueTrigger @1811ea420` -> c'est la condition d'arret de
    la chaine : caster vivant ET cible vivante ET caster a <= `range` hex de la cible. Comme les
    Bloodletters ATTAQUENT la cible a l'apparition, une cible qui MEURT en cours de chaine rend `cond`
    faux -> selecteur vide -> `ChainBehaviour` s'arrete AVANT d'avoir consomme ses `maxSummons`.

    Le predicat reste du DSL (`IsAlive`/`IsInRange`/`TriggerAnd`) et le selecteur de tuiles aussi
    (`CanAddUnit(AdjacentTiles(Target()))`) ; seul le couple `ConditionalAmount`+`PickRandomly` est FOLDE
    (le tirage vit la ou l'on voit `state.rng`, meme doctrine que le `pick_n` de `Spawn`)."""
    from ..abilities.loki.splash import _pick_randomly_n
    rng_const = int(((GC.ability("Incursion") or {}).get("constants") or {}).get("range") or 0)
    cond = TriggerAnd(TriggerAnd(IsAlive(Caster()), IsAlive(Target())),
                      IsInRange(Caster(), Target(), Const(rng_const)))
    if not cond.evaluate(entities):                      # ConditionalAmount -> 0@dsl+0xb8 -> fin de chaine
        return Nothing()
    tiles = CanAddUnit(AdjacentTiles(Target())).evaluate(entities)
    return FixedTileIds(_pick_randomly_n(state, tiles, 1))   # ConditionalAmount -> 1@dsl+0xc0


def incursion_tree(state: "State", max_summons: int) -> ChainBehaviour:
    """Arbre de `IncursionAbility.ExecuteBehaviour @1811e9fe0` : `ChainBehaviour` bornee a `maxSummons`
    iterations, chacune (a) re-evaluant `GetNextSpawnTile` (0 ou 1 tuile libre adjacente a la cible,
    gatee par la condition de continuation) puis (b) executant `Spawn(caster, ActiveTarget@0x180,
    blackSmnBloodletter, opts)` -- la tuile rendue par l'iteration est liee a `ActiveTarget`, que le
    `Spawn` lit comme tile-selecteur. Le sous-behaviour on-appearance des options
    (`UseNormalAttackIfAble(activeTarget@0x180, Entity(cible))`) fait ATTAQUER chaque Bloodletter
    fraichement pose sur la cible du cast -- ici `ActiveTarget` designe le SUMMON (rebind du `Spawn`),
    imbrique dans le bind de tuile de la chaine (mirror exact des deux niveaux natifs)."""
    return ChainBehaviour(next_selector=lambda ents: incursion_next_spawn_tile(state, ents),
                          times=Const(int(max_summons)),
                          body=Spawn(ActiveTarget(), "Incursion",
                                     on_appearance=UseActiveAbility(ActiveTarget(), Target())),
                          init=Null())


# ===================== HadesAutocannons (blackForgefiend, MACHINE OF WAR, actif 1147) =====================
#
# Porteur : `blackForgefiend` « Forgefiend » = MACHINE OF WAR (pool `--list-pool`, 8 MoW) -> entite ECS
# hors-plateau (ni Position ni Health), chargee par `_load_machines` (case-mow-offboard-cast).
#
# CIBLAGE (face DECISION/eligibilite) : 1147 n'a **AUCUN** `GetDynamicInvalidTargetReason` (contraste
# 1168/1200) -- son predicat vit dans les `TargetingOptions` du ctor `HadesAutocannonsAbility..ctor
# @1811e56b0` (`TargetingOptions(0, <filtre>, 1, 0x46006000, 0,0,0)`), ET il est REDIT par le selecteur
# d'execution `GetAllTargets @1811e5480` (`UnitsWithTrait(..., 2=Summon)`) : la cible doit etre un
# **SUMMON ennemi**. C'est CE predicat qui rend « 0 cible au spawn » (sweep case-mow §5) : il faut le
# MONTER (amener un summoner adverse a invoquer, puis viser un summon) pour obtenir une cible.
CONST_HADES_RANGE = 0x16          # GetNumberConstant(0x16) -> "range" = 2
VAR_EXTRA_CRIT_DMG = 0x42         # GetVariableForLevel(0x42) -> "extraCritDmg"
HADES_AUTOCANNONS_ID = "HadesAutocannons"


def hades_autocannons_get_all_targets(range_: int):
    """`HadesAutocannonsAbility.GetAllTargets @1811e5480` — MIRROR du DECOMPILE :

        sel   = UnitsWithTrait( Friends( target@0x178,                                   # allies DE LA CIBLE
                                         SurroundingUnits(target@0x178, GetNumberConstant(0x16)=range,
                                                          1, includeCenter=1, 3) ),
                                2 = Summon, 3 )
        asc   = SortByRow( Tiles(sel), 0, 0, false )
        desc  = SortReverse( SortByRow( Tiles(sel), 0, 0, false ) )
        return If( AreEqual(CurrentPlayer, Player(1)), asc, desc )                        # == IsTopPlayer @1811e5640

    = les SUMMONS (trait 2) allies de la CIBLE, dans un disque de rayon `range` autour d'elle,
    **CIBLE INCLUSE** (`SurroundingTiles(..., includeCenter=1)` @180dfca70 : param!=0 -> selecteur direct,
    param==0 -> `- Tiles(center)`). i2 : « a targeted enemy summon AND all other enemy summons within 2
    hexes of the target ». Le referent de `Friends` est la **CIBLE** (1er arg natif), pas le caster : ce
    sont donc les summons du camp de la cible = les summons ENNEMIS du caster (d'ou le `Friends(reference=
    Target())` porte).

    **ORDRE** : le `SortByRow`/`SortReverse` (+ `If(IsTopPlayer)`) est un ordre de LECTURE du selecteur ;
    il est ECRASE en aval par l'`OrderBy` que `AttackBehaviour.Execute @180fb91a0` applique
    INCONDITIONNELLEMENT des que le set a >= 2 cibles (`if (1 < count) OrderBy(<>c.b__5_0 @180fd9150)`
    = cle par-entite du slot vtable +0x158). Le port garde donc son tri par `id` (`multi=True`, == tous
    les autres multi-cibles valides bit-exact) et NE porte PAS les noeuds de tri — HYPOTHESE explicite
    (la cle +0x158 n'est pas relue ici) : discriminable live avec >= 2 summons dont l'ordre de `row`
    contredit l'ordre d'`id`."""
    from ...entities.selectors import SurroundingUnits, TargetTile, Tiles, Units, UnitsWithTrait
    from ...entities.traits.unit_trait import UnitTrait
    ring = SurroundingUnits(TargetTile(), Const(int(range_)), include_center=True)   # includeCenter=1
    summons = UnitsWithTrait(Friends(ring, reference=Target()), int(UnitTrait.Summon))
    return Units(Tiles(summons))     # aller-retour unites -> Tiles(sel) -> Units(...) du natif (mirror)


def hades_autocannons_tree(range_: int, crit_amount: int, caster_id: int):
    """Arbre de `HadesAutocannonsAbility$$ExecuteBehaviour @1811e50e0` — MIRROR du DECOMPILE :

        crit  = GetVariableForLevel(config, 0x42 = extraCritDmg, abilityState)
        Execute( op_Addition( op_Addition(
            ChangeStat( Owner@0x148, Position(10=CriticalDamage, 0), mode=2=Add, Direct(crit) ),   # [1]
            AttackWithAttackDamage( Owner@0x148, Units(GetAllTargets()),                           # [2]
                                    MinMaxDamage, Direct(GetDamageProfile)=Flame,
                                    Direct(GetHits()=ConfigConst(0x2f)=nrOfHits=6),
                                    AbilityOrEffect(0x47b = 1147), <options> ) ),
            ChangeStat( Owner@0x148, Position(10, 0), mode=3=Subtract, Direct(crit) ) ) )          # [3]

    JUMEAU STRUCTUREL de `HeroicFusilladeAbility @1811e8de0` (buff crit temporaire NET-NUL encadrant
    l'attaque, meme couple ChangeStat Add/Sub sur `CRIT_DAMAGE` avec source PARTAGEE) — d'ou la meme
    feuille portee `ChangeStat(..., "add"/"revert", src)`.

    - **native_factory = "attack"** (defaut) : le decompile appelle `DSLFactory.AttackWithAttackDamage`
      (VERIFIE par la CALLEE de @1811e50e0 ; contraste EntropyCannons/SquigLaunchas =
      `AttackWithAbilityDamage`) -> `AttackDamageOperation.ExecuteHit @180e5eff0`, 2 tirages/coup a cc=0,
      crit ACTIF (c'est justement ce que le buff [1] alimente).
    - `multi=True` : le selecteur resout N cibles -> `AttackBehaviour.Execute @180fb91a0` attaque CHACUNE
      (ordre = OrderBy par-entite, port = tri par id).
    - Profil `Flame` (PiercingRatio 25, trait OnFire), `nrOfHits`=6, `attackRangeType=Ranged` ->
      `is_melee=False`.
    - Le buff crit est INERTE tant que la `CritChance` du caster est 0 (cas d'une MoW seedee a 0 :
      `_load_machine_stats` ; `combatSnapshot` filtre `EntityType.Unit` -> la CritChance resolue d'une
      MoW n'est pas captable, residu case-mow §8). Il est neanmoins porte 1:1 : des que la CritChance
      devient > 0 (i2 : `DaemonicOrdnance` +20 %/usage), le +extraCritDmg s'applique par coup CRITIQUE."""
    from ...entities.behaviours import op_add
    from ...entities.stats import StatType
    from .behaviours import ChangeStat
    src = (f"{HADES_AUTOCANNONS_ID}_CritDamage", caster_id)            # source PARTAGEE add<->revert
    crit_add = ChangeStat(Caster(), int(StatType.CRIT_DAMAGE), "add", src, amount=int(crit_amount))
    attack = AttackWithAttackDamage(hades_autocannons_get_all_targets(range_), HADES_AUTOCANNONS_ID,
                                    "Flame", is_melee=False, multi=True,
                                    ability_type=int(ActiveAbilityType.HadesAutocannons))
    crit_revert = ChangeStat(Caster(), int(StatType.CRIT_DAMAGE), "revert", src)
    return op_add(op_add(crit_add, attack), crit_revert)


class HadesAutocannonsAbility(ActiveAbility):
    """`HadesAutocannonsAbility$$ExecuteBehaviour @1811e50e0` (id 1147, `blackForgefiend` « Forgefiend »,
    MACHINE OF WAR Black Legion). Arbre DSL `hades_autocannons_tree()` (mirror 1:1) : buff CRIT_DAMAGE
    (+extraCritDmg[level]) -> 6 coups Flame sur la cible ET tous les summons de SON camp a <= range hex
    d'elle (`GetAllTargets @1811e5480`) -> retrait du buff.

    Caster = une **MoW hors-plateau** (ni Position ni Health) : `apply_elevation_bonus`/
    `apply_trench_reduction` (famille ATTACK) no-op sans position d'attaquant -> aucun chemin ne suppose
    une tuile de caster. Turn-flags = defauts base (1147 absent des overrides).
    Diag : {crit_amount, targets, attacks:[{target,total}]}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HadesAutocannons)   # 1147
    ABILITY_ID = HADES_AUTOCANNONS_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        from ...entities.effects.magnitude import ability_var
        from ..components import StatsComponent
        if target_id is None:
            return None
        sc = state.get_entity(caster_id).get_component(StatsComponent) if state.get_entity(caster_id) else None
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        crit = int(ability_var(self.ABILITY_ID, "extraCritDmg", level, multiplier_pct=mult) or 0)
        rng_const = int(((GC.ability(self.ABILITY_ID) or {}).get("constants") or {}).get("range") or 0)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        hades_autocannons_tree(rng_const, crit, caster_id).execute(entities, ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "crit_amount": crit, "range": rng_const,
                "targets": [a["target"] for a in attacks], "attacks": attacks, "dsl": True}


class IncursionAbility(ActiveAbility):
    """`IncursionAbility.ExecuteBehaviour @1811e9fe0` (id 1021, `blackPossession` "Vitruvius",
    BlackLegion). Invoque JUSQU'A `maxSummons`=6 Bloodletters (`blackSmnBloodletter`), UN PAR ITERATION,
    sur des tuiles LIBRES adjacentes a la cible ; chaque Bloodletter attaque la cible a son apparition.
    La chaine s'arrete des qu'une tuile manque OU que la condition de continuation
    (`GetContinueTrigger @1811ea420` : caster vivant & cible vivante & caster a <= `range`=2 hex) tombe --
    typiquement quand les Bloodletters ONT TUE la cible.

    N'utilise PAS `PerformAIAction` (contrairement a ce que suggerait le regroupement de tache : la face
    COMBAT de 1021 passe par `ChainBehaviour` + on-appearance `UseNormalAttackIfAble`).
    Retour : {spawned, attacks, max_summons, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Incursion)   # 1021
    ABILITY_ID = "Incursion"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        max_summons = int(consts.get("maxSummons") or 0)      # GetNumberConstant(0x3c)
        ectx = ExecutionContext(state=state, rng=state.rng)
        incursion_tree(state, max_summons).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [p for n, p in ectx.emitted if n == "UseActiveAbility"]
        return {"spawned": spawned, "attacks": attacks, "max_summons": max_summons, "dsl": True}
