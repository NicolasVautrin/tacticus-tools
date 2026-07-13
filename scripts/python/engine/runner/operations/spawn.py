"""Spawn d'unité SUMMON — port de `ScarabHiveAbility.ExecuteBehaviour @181204cb0` (ability du SUMMONER)
→ `DSLFactory.Spawn` → `AddUnitOperation.Execute`.

GROUND TRUTH (RE ghidra + live, cf. project_summon_team_model) — `ScarabHiveAbility @181204cb0` (necroSpyder) :
  - **visualId** = `GetStringConstant(config, 0)` = `gameconfig.ability(ScarabHive).constants["unitId"]`
    = `necroSmnSwarm` ;
  - **count**    = nb d'invocations de l'ability (ScarabHive = `2`, arg du `.ctor AActiveAbility`) ;
  - **placement**= `AdjacentTiles(target@0x178)` → `CanAddUnit` → `SortByDistance(self@0x160)` → `First` =
    tuiles LIBRES adjacentes à la **CIBLE**, la plus proche du caster (cf. `GetPossibleSpawnTiles @181205100`) ;
  - **owner**    = team ET player du caster (validé live team=1 player=3 ; ≠ PlayerIdGenerator) ;
  - **stats**    = `ability_var(ScarabHive, summonHp/summonDmg/summonArmor/summonCritChance/summonCritDmg,
    casterActiveAbilityLevel, casterMultiplier)` (clés `variablesAffectedByRarityBonus` → ×multiplier) ;
  - **effet posé** = `AddEffect(0x4a3)` = `ScarabHive_OverrideDamageProfileEffect` sur le scarab spawné ;
  - **on-appearance** = `UseNormalAttackIfAble` (attaque normale immédiate — PAS `PerformAIAttack`).

Le scarab spawné (`necroSmnSwarm`) porte SON PROPRE kit — DÉCISIF pour `ai_controlled` (cf. #65) :
  - **trait `Summon`** = « Moves and attacks automatically at the beginning of its turn » → il est joué
    par l'IA au TURN-START de sa team (passe AI-control `run_ai_control_pass`), un chemin SÉPARÉ de
    `PickNextUnit`/`aiStepDryRun`. Le scarab N'EST PAS apparition-only → `ai_controlled=True`.
  - **active `ScarabSummon` @181205290** = auto-DÉDOUBLEMENT : `AdjacentTiles(self@0x160)` → `PickRandomly`
    → `CopyOwner` → `Spawn` un AUTRE `necroSmnSwarm` adjacent à SOI, dont l'on-appearance = `PerformAIAttack`
    (« which then immediately takes a turn ») → c'est le DOUBLE qui attaque. Playbook `ScarabSummonPlaybook`
    (`GetUseProbability` = 1.0 ou 1/2 selon un compteur runtime ; `chance` gameconfig = 50).
  - **passive `ReanimationProtocols`** = revive-on-death (chance 35 %, 25 % PV) hors overkill.

VALIDÉ live bit-exact : necroSpyder (activeAbilityLevel=50, mult=200) ScarabHive → 2× necroSmnSwarm
**team=1 player=3 hp=2218 dmg=998** ; `ability_var(ScarabHive, summonHp, 50, 200)=2218`.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import (StatsComponent, OwnerComponent, PositionComponent,
                          HealthComponent, UnitComponent)
from ...entities.traits import UnitTrait, has_trait


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
        active_ability_level=int(caster_level or 0),   # niveau du caster -> propage aux self-summons (PileIn 2e gen)
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


def _occupied_tiles(state: State) -> set:
    """Ids de tuiles occupées par une unité VIVANTE (ou sans UnitComponent = objet/décor) — pour `CanAddUnit`."""
    board = state.board
    out: set = set()
    if board is None:
        return out
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None:
            continue
        if uc is not None and not uc.alive:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            out.add(t)
    return out


def _spawn_config_grot(state: State, visual_id: str, tile, summon_ability: str,
                       level, mult: int, team, player) -> Optional[int]:
    """Spawn UNE unité `visual_id` sur `tile` (id de tuile), stats `WithStatsFromConfig(summon_ability)` =
    `ability_var(summon_ability, summon*, level, mult)`, owner = team+player, `active_ability_level = level`
    (propagé → lève le GAP PileIn 2e-gen). Renvoie l'entity id (None si `tile` None). Partagé par
    GetEmRuntz/SquigHound (WithStatsFromConfig, PAS clone)."""
    if tile is None:
        return None
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=True))
    e.add_component(OwnerComponent(team=team, player=player))
    ctx = build_summon_context(e.id, visual_id, summon_ability, level, mult)   # set active_ability_level=level
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=ctx.health, hp_max=ctx.health))
    _seed_trait_owner_effects(state, e.id, ctx.traits, mult)
    _seed_derived_ability_owner_effects(state, e.id, ctx.traits, mult)
    _maybe_seed_ignore_battle_fatigue(state, e.id, team, mult)   # aura SquigHound -> grots amis immunisés
    board = state.board
    tinfo = board.by_id.get(tile) if board is not None else None
    if tinfo is not None:
        e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
    return e.id


IGNORE_BATTLE_FATIGUE = 0x437    # 1079 — status IgnoreBattleFatigue vérifié par BattleFatigueAbility (behaviour.py)


def _team_has_squighound(state: State, team) -> bool:
    """La team a-t-elle un porteur VIVANT du passif `SquigHound` (Snotflogga) ? = source de l'aura."""
    import gameconfig as GC
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive or oc.team != team:
            continue
        if "SquigHound" in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
            return True
    return False


def _maybe_seed_ignore_battle_fatigue(state: State, unit_id: int, team, mult: int) -> bool:
    """`SquigHound_IgnoreBattleFatigueEffect @180f6d210` (aura de Snotflogga sur les grots amis) : si la team
    a un porteur `SquigHound` VIVANT, pose l'effet `IgnoreBattleFatigue`(1079=0x437) sur l'unité → immunisée
    du flee `BattleFatigue` (gate déjà porté `behaviour.py:121` : `NOT HasEffect(self, 1079)`). Idempotent.
    ⚠ Snapshot au spawn : le retrait de l'aura si Snotflogga meurt N'EST PAS modélisé (grot garde l'immunité)."""
    if not _team_has_squighound(state, team):
        return False
    from ...entities.effects import EffectFactory
    from ...entities import EffectsState
    if state.effects is None:
        state.effects = EffectsState.seed({})
    if state.effects.has_effect(unit_id, effect_type=IGNORE_BATTLE_FATIGUE):
        return False
    eff = EffectFactory.create({"name": "IgnoreBattleFatigue", "effectType": IGNORE_BATTLE_FATIGUE,
                                "remaining": 0}, ability_variables_multiplier=int(mult or 100))
    eff.target = unit_id
    state.effects.add_effect(unit_id, eff)
    return True


def _materialize_owner_effect(state: State, unit_id: int, name: str, mult: int) -> bool:
    """Matérialise UN owner-effect (par nom) sur l'unité dans `EffectsState`, PERMANENT (rem=None), comme les
    unités initiales seedées depuis capture — pour que `attacker_modifiers`/`defender_modifiers` (qui lisent
    `state.effects`) le voient. Idempotent (gate `has_effect`). Renvoie True si ajouté."""
    from ...entities.effects import EffectFactory
    from ...entities import EffectsState
    if state.effects is None:
        state.effects = EffectsState.seed({})
    if state.effects.has_effect(unit_id, name=name):
        return False                                         # déjà présent
    eff = EffectFactory.create({"name": name, "remaining": 0},   # rem 0 -> permanent
                               ability_variables_multiplier=int(mult or 100))
    eff.target = unit_id
    state.effects.add_effect(unit_id, eff)
    return True


def _seed_trait_owner_effects(state: State, unit_id: int, traits, mult: int) -> list:
    """`InitializeActorAbilitiesOperation.Execute` @180e74660 (boucle TRAITS) : à la création d'unité, CHAQUE
    trait ajoute à son PORTEUR les owner-effects de `StaticBattleRules.Trait.GetEffectToBeAddedToOwnerForTrait`
    @18157e800 (dict `Trait..cctor` @18157f650 +0x30). Sans ce seed, un summon SPAWNÉ n'a AUCUN effet -> ses
    traits de dégât (HeavyWeapon +25% ranged, RangedSpecialist +33% ranged, ...) ne s'appliquent PAS à ses
    attaques (gap corrigé)."""
    from ...entities.effects.factory import get_effect_to_be_added_to_owner_for_trait
    return [name for tr in (traits or [])
            for name in get_effect_to_be_added_to_owner_for_trait(tr)
            if _materialize_owner_effect(state, unit_id, name, mult)]


def _seed_derived_ability_owner_effects(state: State, unit_id: int, traits, mult: int) -> list:
    """Chemin trait -> ability DÉRIVÉE -> owner-effect posé à l'INIT de l'ability (mécanisme DISTINCT des 2
    dicts owner-effect directs). Mirror `AddTraitOperation.AddDerivedAbilities @180e513c0` (trait -> ability,
    dict Trait +0x0/+0x8) puis `<Ability>.CreateBehaviour` (DSL `AddEffect(owner)` à l'init de l'ability).

    Cas porté : trait **BigTarget** -> ability `BigTarget` (0x406) -> `BigTargetAbility.CreateBehaviour
    @18121a910` = `AddEffect(BigTarget_AdjacentEffect)` (aura -1 hit ranged aux alliés ring-1, source-side).
    Les autres traits summon dérivent aussi une ability mais leur owner-effect à l'init n'est pas encore LU
    (cf. `factory.ABILITY_INIT_OWNER_EFFECTS`) -> non seedés (fidélité-safe)."""
    from ...entities.effects.factory import (get_derived_abilities_for_trait,
                                             get_owner_effects_added_on_ability_init)
    added: list = []
    for tr in (traits or []):
        for ab in get_derived_abilities_for_trait(tr):
            for name in get_owner_effects_added_on_ability_init(ab):
                if _materialize_owner_effect(state, unit_id, name, mult):
                    added.append(name)
    return added


TELEPORT_STRIKE_TELEPORTING_IN = 1035    # AbilityOrEffect.TeleportStrike_TeleportingIn (0x40b) — etat deep-strike


def _seed_ability_owner_effects(state: State, unit_id: int, vid: str, mult: int) -> list:
    """`InitializeActorAbilitiesOperation.Execute @180e74660` (boucle ABILITIES) : pour chaque ability de
    l'unite, l'owner-effect pose par son `CreateBehaviour` a l'init (DSL `AddEffect(owner)`). Ex. passive
    `PathOfCommand` -> `PathOfCommand_ExtraDmg` (aura +Attack). Abilities lues de gameconfig (active+passive)."""
    import gameconfig as GC
    from ...entities.effects.factory import get_owner_effects_added_on_ability_init
    gu = GC.unit(vid) or {}
    abilities = list(gu.get("activeAbilities") or []) + list(gu.get("passiveAbilities") or [])
    return [name for ab in abilities
            for name in get_owner_effects_added_on_ability_init(ab)
            if _materialize_owner_effect(state, unit_id, name, mult)]


def land_deep_strike(state: State, unit_id: int) -> Optional[dict]:
    """ATTERRISSAGE d'une unite TeleportStrike (deep-strike). Ground truth live (probe ds_landing) : a la FIN
    du 1er tour de son proprietaire, l'unite passe de « teleporting-in » (effet 1035, non-ciblable, passives
    NON initialisees) a « posee » -> TeleportStrike_TeleportingIn RETIRE + `InitializeActorAbilities` (init des
    passives deferrees = owner-effects des abilities+traits, ex. aura `PathOfCommand_ExtraDmg`) -> ciblable +
    auras projettent. No-op si l'unite n'est pas teleporting-in."""
    if state.effects is None or not state.effects.has_effect(
            unit_id, effect_type=TELEPORT_STRIKE_TELEPORTING_IN):
        return None
    for e in state.effects.by_unit.get(int(unit_id), []):     # retire TeleportingIn (consomme l'instance)
        if not e.consumed and e.effect_type == TELEPORT_STRIKE_TELEPORTING_IN:
            e.consumed = True
    ent = state.get_entity(unit_id)
    uc = ent.get_component(UnitComponent) if ent is not None else None
    sc = ent.get_component(StatsComponent) if ent is not None else None
    ctx = sc.ctx if sc is not None else None
    vid = uc.visual_id if uc is not None else ""
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    traits = list(getattr(ctx, "traits", None) or [])
    added = _seed_ability_owner_effects(state, unit_id, vid, mult)      # ex. PathOfCommand -> aura +Attack
    added += _seed_trait_owner_effects(state, unit_id, traits, mult)    # owner-effects des traits (idempotent)
    added += _seed_derived_ability_owner_effects(state, unit_id, traits, mult)
    return {"landed": unit_id, "owner_effects_added": added}


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
            # ai_controlled : le summon (trait `Summon` = « moves and attacks automatically at the beginning
            # of its turn ») est joué par l'IA au TURN-START de sa team via `run_ai_control_pass` (#65) —
            # mirroir du flag runtime `IsPlayerAiControlled` @1804d7b10. TOUS les summons d'ability sont
            # ai_controlled : le scarab s'auto-dédouble (`ScarabSummon` @181205290) + attaque, jamais inerte
            # (cf. docstring module). PAS de gate apparition-only (le « 0 action » via aiStepDryRun etait un
            # artefact de sonde : ce chemin ne DRIVE PAS la passe AI-control turn-start).
            e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=True))
            e.add_component(OwnerComponent(team=coc.team, player=coc.player))   # CopyOwner
            ctx = build_summon_context(e.id, visual_id, summon_ability, level, mult)
            e.add_component(StatsComponent(ctx=ctx))
            e.add_component(HealthComponent(hp=ctx.health, hp_max=ctx.health))
            # [InitializeActorAbilitiesOperation boucle TRAITS] owner-effects des traits du summon dans
            # EffectsState (sinon ses traits de dégât ne s'appliquent pas à ses attaques — gap corrigé).
            _seed_trait_owner_effects(state, e.id, ctx.traits, mult)
            # [trait -> ability dérivée -> AddEffect(owner) à l'init] ex. BigTarget -> BigTarget_AdjacentEffect.
            _seed_derived_ability_owner_effects(state, e.id, ctx.traits, mult)
            if tile is not None and board is not None:
                tinfo = board.by_id.get(tile)
                if tinfo is not None:
                    e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
                    chosen.add(tile)
            spawned.append(e.id)
        # NB on-appearance (`UseNormalAttackIfAble`) = tranche ultérieure (les ids spawnés sont renvoyés ;
        # `Entity`/`State` ont __slots__ → pas de marqueur posé ici).
        return spawned

    @staticmethod
    def execute_self_replica(state: State, caster_id: int, visual_id: str, count: int = 1) -> list:
        """`ScarabSummonAbility.ExecuteBehaviour @181205290` (auto-DÉDOUBLEMENT) : le summon s'invoque
        LUI-MÊME. Spawn `count` clones sur des tuiles LIBRES adjacentes au **CASTER** (self@0x160), owner+
        stats = `SpawnUnitOptions.CopyOwner(caster) @180fd5ba0` (owner du caster + STATS clonées du parent).

        CopyOwner (RE @180fd5ba0) copie les StatType `{0=Attack, 1=Movement, 5=Health, 16=Armor, 20}` du
        caster (`StatAmount(..., StatPart=3)`) puis `CreateSpawnOptions(owner)` — PAS de WithStatsFromConfig.
        Les stats NON copiées (crit/block/hits) viennent de la config de base ; comme le parent EST un
        `necroSmnSwarm` (même type que le clone), elles sont identiques → on clone le ctx entier du parent.
        Distinct de `execute` (ScarabHive : adjacent-CIBLE + stats `ability_var` summoner-scaled)."""
        from dataclasses import replace as _dc_replace
        from ...entities.stats import UnitStats, StatType
        caster = state.get_entity(caster_id)
        if caster is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        c_ctx = csc.ctx if csc is not None else None
        if coc is None or c_ctx is None:
            return []
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        clone_stats = (StatType.ATTACK, StatType.MOVEMENT, StatType.HEALTH, StatType.FIXED_ARMOR,
                       StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE, StatType.BLOCK_CHANCE,
                       StatType.BLOCK_DAMAGE, StatType.EXTRA_HITS)
        spawned: list = []
        chosen: set = set()
        board = state.board
        for _ in range(max(0, int(count))):
            tiles = _free_tiles_adjacent(state, caster_id, chosen)   # adjacent au CASTER (self@0x160)
            tile = _pick_randomly(state, tiles)
            e = state.add_entity()
            e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=True))
            e.add_component(OwnerComponent(team=coc.team, player=coc.player))       # CopyOwner (owner)
            rep_stats = UnitStats()                              # CopyOwner (stats) : clone identité du parent
            for st in clone_stats:
                rep_stats.ensure_seeded(int(st), c_ctx.get_stat(int(st), 0))
            ctx = _dc_replace(c_ctx, entity_id=e.id, stats=rep_stats)
            e.add_component(StatsComponent(ctx=ctx))
            e.add_component(HealthComponent(hp=ctx.health, hp_max=ctx.health))
            _seed_trait_owner_effects(state, e.id, ctx.traits, mult)
            _seed_derived_ability_owner_effects(state, e.id, ctx.traits, mult)
            if tile is not None and board is not None:
                tinfo = board.by_id.get(tile)
                if tinfo is not None:
                    e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
                    chosen.add(tile)
            spawned.append(e.id)
        return spawned

    @staticmethod
    def execute_pilein_replica(state: State, parent_id: int) -> list:
        """`PileInAbility.CreateBehaviour @181223990` — auto-DÉDOUBLEMENT du grot (PASSIF fin-de-tour).
        Spawn UN grot sur une tuile LIBRE ring-1 adjacente au parent, **stats = `WithStatsFromConfig(PileIn)`**
        = `ability_var(PileIn, summon*, level, mult)` — PAS un clone (le grot PileIn = ~0.606× le grot
        GetEmRuntz : 2910 vs 4802 PV @lvl65/mult100). Renvoie [id] ou [].

        `level`/`mult` = ceux du parent (`active_ability_level`/`ability_variables_multiplier`, propagés depuis
        le summoner). ⚠ GAP : un grot SEEDÉ depuis un combatSnapshot live n'a PAS de `active_ability_level`
        (level=0) → stats PileIn fausses ; il faut un GetEmRuntz porté (ou le level capté) pour résoudre.
        Placement natif = `First(SortByFormula(Randomize(CanAddUnit(AdjacentTiles(self)))))` ; ici
        `PickRandomly` (formule de tri = raffinement)."""
        import gameconfig as GC
        parent = state.get_entity(parent_id)
        if parent is None:
            return []
        coc = parent.get_component(OwnerComponent)
        csc = parent.get_component(StatsComponent)
        p_ctx = csc.ctx if csc is not None else None
        if coc is None or p_ctx is None:
            return []
        visual_id = ((GC.ability("PileIn") or {}).get("constants") or {}).get("summonId")   # orksGrot
        if visual_id is None:
            return []
        level = getattr(p_ctx, "active_ability_level", None)
        mult = int(getattr(p_ctx, "ability_variables_multiplier", 100) or 100)
        tiles = _free_tiles_adjacent(state, parent_id, set())
        tile = _pick_randomly(state, tiles)
        if tile is None:
            return []                                        # aucune tuile ring-1 libre -> pas de spawn
        e = state.add_entity()
        e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=True))
        e.add_component(OwnerComponent(team=coc.team, player=coc.player))
        ctx = build_summon_context(e.id, visual_id, "PileIn", level, mult)   # WithStatsFromConfig(PileIn)
        e.add_component(StatsComponent(ctx=ctx))
        e.add_component(HealthComponent(hp=ctx.health, hp_max=ctx.health))
        _seed_trait_owner_effects(state, e.id, ctx.traits, mult)
        _seed_derived_ability_owner_effects(state, e.id, ctx.traits, mult)
        _maybe_seed_ignore_battle_fatigue(state, e.id, coc.team, mult)   # aura SquigHound -> grot immunisé
        board = state.board
        tinfo = board.by_id.get(tile) if board is not None else None
        if tinfo is not None:
            e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
        return [e.id]

    @staticmethod
    def execute_getemruntz(state: State, caster_id: int) -> list:
        """`GetEmRuntzAbility.ExecuteBehaviour @1811e2210` (id 1045, orksRuntherd/Snotflogga). Spawn UN grot
        dans CHAQUE hex LIBRE adjacent au caster **ET** adjacent à un ennemi (`GetSpawnTileSelector @1811e26b0`
        = `CanAddUnit(AdjacentTiles(caster)) & AdjacentTiles(Enemies − trait0x1b)`), stats
        `WithStatsFromConfig(GetEmRuntz)` = `ability_var(GetEmRuntz, summon*, casterLevel, mult)` (4802 PV @lvl65).

        Chaque grot porte `active_ability_level = casterLevel` (via `build_summon_context`) → **lève le GAP
        PileIn** (le grot pourra résoudre `ability_var(PileIn, ..., casterLevel)`). On-appearance
        `PerformAIAttackFromCurrentPosition` + Taunt(1t) des ennemis touchés = FLAGGÉ non porté (secondaire).
        Exclusion `UnitsWithoutTrait(0x1b=27=Steppable)` PORTÉE (#135, même mapping que ArcaneShield) : les
        ennemis Steppable (tokens marchables decoys/mines) ne comptent pas dans l'adjacence de spawn."""
        caster = state.get_entity(caster_id)
        board = state.board
        if caster is None or board is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        cpc = caster.get_component(PositionComponent)
        c_ctx = csc.ctx if csc is not None else None
        if coc is None or c_ctx is None or cpc is None:
            return []
        level = getattr(c_ctx, "active_ability_level", None)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        vid = ((__import__("gameconfig").ability("GetEmRuntz") or {}).get("constants") or {}).get("unitId")
        if vid is None:
            return []
        ctile = board.id_at(cpc.col, cpc.row)
        if ctile is None:
            return []
        occupied = _occupied_tiles(state)
        # tuiles adjacentes à un ennemi VIVANT du caster (Enemies -> AdjacentTiles)
        enemy_adjacent: set = set()
        for e in state.entities.values():
            oc = e.get_component(OwnerComponent)
            uc = e.get_component(UnitComponent)
            pc = e.get_component(PositionComponent)
            if oc is None or pc is None or oc.team == coc.team:
                continue
            if uc is not None and not uc.alive:
                continue
            # `Enemies − trait0x1b` : exclut les ennemis Steppable (UnitTrait 0x1b=27, tokens marchables
            # decoys/mines) du comptage d'adjacence. Gate via `has_trait` (#146 : mapping id<->nom centralisé
            # dans UnitTrait ; même fix int-vs-str que ArcaneShield #135).
            esc = e.get_component(StatsComponent)
            if esc is not None and has_trait(esc.ctx.traits, UnitTrait.Steppable):
                continue
            et = board.id_at(pc.col, pc.row)
            if et is not None:
                enemy_adjacent.update(board.neighbours(et))
        # spawn tiles = adjacentes-caster LIBRES ∩ adjacentes-ennemi (déterministe : trié)
        spawn_tiles = [t for t in sorted(board.neighbours(ctile))
                       if board.walkable(t) and t not in occupied and t in enemy_adjacent]
        spawned: list = []
        for t in spawn_tiles:
            gid = _spawn_config_grot(state, vid, t, "GetEmRuntz", level, mult, coc.team, coc.player)
            if gid is not None:
                spawned.append(gid)
        return spawned

    @staticmethod
    def execute_squighound_summon(state: State, caster_id: int, target_id: int) -> list:
        """`SquigHoundSummonUnitAbility.CreateBehaviour @1811a1a30` (passif triggé, orksRuntherd). APRÈS une
        attaque du caster (trigger `On(0x26)` — cf. wiring after-hit), si **< maxSummons(5)** grots amis, spawn
        1 grot sur la MEILLEURE tuile LIBRE adjacente à la CIBLE (`AdjacentTiles(target) SortTilesByUtilityForSummon
        First`), stats `WithStatsFromConfig(SquigHound)` (4802 PV @lvl65), `active_ability_level = casterLevel`
        (→ lève le GAP PileIn). On-appearance `PerformAIAttack` = FLAGGÉ non porté. Renvoie [id] ou []."""
        import gameconfig as GC
        caster = state.get_entity(caster_id)
        board = state.board
        if caster is None or board is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        c_ctx = csc.ctx if csc is not None else None
        if coc is None or c_ctx is None:
            return []
        consts = (GC.ability("SquigHound") or {}).get("constants") or {}
        vid = consts.get("unitId")
        max_summons = int(consts.get("maxSummons") or 5)
        if vid is None:
            return []
        # condition : NOT (grots amis >= maxSummons)  ->  strictement < maxSummons
        n_grots = sum(1 for e in state.entities.values()
                      if (u := e.get_component(UnitComponent)) is not None and u.alive and u.visual_id == vid
                      and (o := e.get_component(OwnerComponent)) is not None and o.team == coc.team)
        if n_grots >= max_summons:
            return []
        tgt = state.get_entity(target_id)
        tp = tgt.get_component(PositionComponent) if tgt is not None else None
        if tp is None:
            return []
        ttile = board.id_at(tp.col, tp.row)
        if ttile is None:
            return []
        occupied = _occupied_tiles(state)
        cands = [t for t in sorted(board.neighbours(ttile)) if board.walkable(t) and t not in occupied]
        tile = _pick_randomly(state, cands)         # SortTilesByUtilityForSummon+First = raffinement (1re libre)
        level = getattr(c_ctx, "active_ability_level", None)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        gid = _spawn_config_grot(state, vid, tile, "SquigHound", level, mult, coc.team, coc.player)
        return [gid] if gid is not None else []
