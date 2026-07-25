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
                                   CasterTile, Damageable, Enemies, FixedTileIds, Nothing, Null, Sub,
                                   Target)
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
