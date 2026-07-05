"""Spawn d'unité SUMMON — port de la chaîne `<X>SummonAbility.ExecuteBehaviour` →
`DSLFactory.Spawn` → `AddUnitOperation.Execute`.

GROUND TRUTH (RE + live, cf. project_summon_team_model) — exemple `ScarabSummonAbility`@181205290 :
  - **visualId** = `GetStringConstant(config, 0)` = `gameconfig.ability(<summon>).constants["unitId"]`
    (ex. ScarabHive → `necroSmnSwarm`) ;
  - **count**    = nb d'invocations de l'ability (ScarabHive = `2`, arg du `.ctor AActiveAbility`) ;
  - **placement**= `PickRandomly(CanAddUnit(AdjacentTiles(target@0x160)), 1)` = tuile LIBRE adjacente à
    la **CIBLE** (pas au caster) ;
  - **owner**    = `SpawnUnitOptions.CopyOwner(caster)` → **team ET player du caster** (≠ PlayerIdGenerator,
    branche non prise pour les summons d'ability — tranché live) ;
  - **stats**    = `ability_var(<summon>, summonHp/summonDmg/summonArmor/summonCritChance/summonCritDmg,
    casterActiveAbilityLevel, casterMultiplier)` (clés `variablesAffectedByRarityBonus` → ×multiplier) ;
  - **on-appearance** = `PerformAIAttack` (attaque immédiate) — marqué (`acts_on_appearance`), l'exécution
    de l'attaque = tranche ultérieure (playbook/turn-flow).

VALIDÉ live bit-exact : necroSpyder (activeAbilityLevel=50, mult=200) ScarabHive → 2× necroSmnSwarm
**team=1 player=3 hp=2218 dmg=998** ; `ability_var(ScarabHive, summonHp, 50, 200)=2218`.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import (StatsComponent, OwnerComponent, PositionComponent,
                          HealthComponent, UnitComponent)


def build_summon_context(entity_id: int, visual_id: str, summon_ability: str,
                         caster_level: Optional[int], caster_mult: int):
    """`UnitContext` d'un summon, résolu 100% offline depuis gameconfig :
      - stats de combat = `ability_var(summon_ability, summon*, caster_level, caster_mult)` ;
      - arme/traits/profil = gameconfig de l'unité summon (`visual_id`).
    `caster_level` = `activeAbilityLevel` du caster ; `caster_mult` = `abilityVariablesMultiplier`. Une clé
    `summon*` absente → 0 (ex. ScarabHive n'a pas `summonArmor` → armure 0, cohérent i2 « 0 Armour »)."""
    import gameconfig as GC
    from ...entities import UnitContext
    from ...entities.effects.magnitude import ability_var
    from ...entities.stats import UnitStats, StatType

    def sv(key: str) -> int:
        v = ability_var(summon_ability, key, caster_level, multiplier_pct=caster_mult)
        return int(v) if v is not None else 0

    gu = GC.unit(visual_id) or {}
    weapons = gu.get("weapons") or []
    w = weapons[0] if weapons else None
    prof_name = w.get("DamageProfile") if w else None
    prof_pierce = 0
    ranged = False
    w_hits = 1
    if w:
        dp = GC.damage_profile(prof_name) or {}
        prof_pierce = int(dp.get("PiercingRatio") or 0)
        w_hits = int(w.get("hits") or 1)
        ranged = bool(w.get("Range"))
    # Les 8 stats de base sont des propriétés `get_stat` → on SEEDE `UnitStats` (au lieu de champs plats).
    # Base identité (ni delta ni mod) depuis les variables `summon*` ; les clés absentes (block/hits) = 0.
    stats = UnitStats()
    for st, key in ((StatType.ATTACK, "summonDmg"), (StatType.HEALTH, "summonHp"),
                    (StatType.FIXED_ARMOR, "summonArmor"), (StatType.CRIT_CHANCE, "summonCritChance"),
                    (StatType.CRIT_DAMAGE, "summonCritDmg")):
        stats.ensure_seeded(st, sv(key))
    for st in (StatType.BLOCK_CHANCE, StatType.BLOCK_DAMAGE, StatType.EXTRA_HITS):
        stats.ensure_seeded(st, 0)
    return UnitContext(
        entity_id=entity_id, visual_id=visual_id,
        ability_variables_multiplier=caster_mult,
        traits=list(gu.get("traits") or []),
        range=int(w.get("Range") or 0) if w else 0,
        faction=gu.get("FactionId"),
        number_of_members=max(1, int(gu.get("nrOfMembers") or 1)),
        normal_profile=prof_name, normal_profile_pierce=prof_pierce,
        normal_weapon_hits=max(1, w_hits), normal_ranged=ranged,
        stats=stats,
    )


def _free_tiles_adjacent(state: State, target_id: int, exclude: set) -> list:
    """`CanAddUnit(AdjacentTiles(target))` — tuiles voisines (evenq) de la cible, marchables et NON
    occupées (par une unité vivante OU une tuile déjà choisie ce spawn). Triées (déterministe) pour
    `PickRandomly`. [] si pas de board."""
    board = state.board
    tgt = state.get_entity(target_id)
    if board is None or tgt is None:
        return []
    tp = tgt.get_component(PositionComponent)
    if tp is None:
        return []
    ttile = board.id_at(tp.col, tp.row)
    if ttile is None:
        return []
    occupied = set(exclude)
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None:
            continue
        if uc is not None and not uc.alive:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occupied.add(t)
    out = [t for t in sorted(board.neighbours(ttile))
           if board.walkable(t) and t not in occupied]
    return out


def _pick_randomly(state: State, tiles: list):
    """`PickRandomly(tiles, 1)` — UNE tuile. n==1 → l'unique ; sinon index `next_internal(0,n)` (coût RNG
    exact à confirmer live ; placement RNG-exact = raffinement, cf. structure d'abord)."""
    if not tiles:
        return None
    if len(tiles) == 1 or state.rng is None:
        return tiles[0]
    return tiles[state.rng.next_internal(0, len(tiles))]


class SpawnUnitOperation:
    """Crée `count` unités summon de type `visual_id`, owner = caster (team+player), placées sur des tuiles
    libres adjacentes à la cible, stats résolues depuis `summon_ability`. Renvoie la liste des entityId
    spawnés. Marque chaque summon `acts_on_appearance` (attaque immédiate, exécutée ailleurs)."""

    @staticmethod
    def execute(state: State, caster_id: int, target_id: int, summon_ability: str,
                visual_id: str, count: int) -> list:
        caster = state.get_entity(caster_id)
        if caster is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        if coc is None:
            return []
        c_ctx = csc.ctx if csc is not None else None
        level = getattr(c_ctx, "active_ability_level", None) if c_ctx else None
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100) if c_ctx else 100
        spawned: list = []
        chosen: set = set()
        board = state.board
        for _ in range(max(0, int(count))):
            tiles = _free_tiles_adjacent(state, target_id, chosen)
            tile = _pick_randomly(state, tiles)
            e = state.add_entity()                           # id auto (≠ live ; confront par vis/team/pos)
            e.add_component(UnitComponent(visual_id=visual_id, alive=True))
            e.add_component(OwnerComponent(team=coc.team, player=coc.player))   # CopyOwner
            ctx = build_summon_context(e.id, visual_id, summon_ability, level, mult)
            e.add_component(StatsComponent(ctx=ctx))
            e.add_component(HealthComponent(hp=ctx.health, hp_max=ctx.health))
            if tile is not None and board is not None:
                tinfo = board.by_id.get(tile)
                if tinfo is not None:
                    e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
                    chosen.add(tile)
            spawned.append(e.id)
        # NB on-appearance (`PerformAIAttack`) = tranche ultérieure (les ids spawnés sont renvoyés ;
        # `Entity`/`State` ont __slots__ → pas de marqueur posé ici).
        return spawned
