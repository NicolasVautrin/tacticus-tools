"""Spawn d'unité SUMMON — port de `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` (ability du SUMMONER)
→ `DSLFactory.Spawn` → `AddUnitOperation.Execute`.

GROUND TRUTH (RE ghidra + live, cf. project_summon_team_model) — `ScarabHiveAbility IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` (necroSpyder) :
  - **visualId** = `GetStringConstant(config, 0)` = `gameconfig.ability(ScarabHive).constants["unitId"]`
    = `necroSmnSwarm` ;
  - **count**    = nb d'invocations de l'ability (ScarabHive = `2`, arg du `.ctor AActiveAbility`) ;
  - **placement**= `AdjacentTiles(target@0x178)` → `CanAddUnit` → `SortByDistance(self@0x160)` → `First` =
    tuiles LIBRES adjacentes à la **CIBLE**, la plus proche du caster (cf. `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$GetPossibleSpawnTiles`) ;
  - **owner**    = team ET player du caster (validé live team=1 player=3 ; ≠ PlayerIdGenerator) ;
  - **stats**    = `ability_var(ScarabHive, summonHp/summonDmg/summonArmor/summonCritChance/summonCritDmg,
    casterActiveAbilityLevel, casterMultiplier)` (clés `variablesAffectedByRarityBonus` → ×multiplier) ;
  - **effet posé** = `AddEffect(0x4a3)` = `ScarabHive_OverrideDamageProfileEffect` sur le scarab spawné ;
  - **on-appearance** = `UseNormalAttackIfAble` (attaque normale immédiate — PAS `PerformAIAttack`).

Le scarab spawné (`necroSmnSwarm`) porte SON PROPRE kit — DÉCISIF pour `ai_controlled` (cf. #65) :
  - **trait `Summon`** = « Moves and attacks automatically at the beginning of its turn » → il est joué
    par l'IA au TURN-START de sa team (passe AI-control `run_ai_control_pass`), un chemin SÉPARÉ de
    `PickNextUnit`/`aiStepDryRun`. Le scarab N'EST PAS apparition-only → `ai_controlled=True`.
  - **active `ScarabSummon` IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour** = auto-DÉDOUBLEMENT : `AdjacentTiles(self@0x160)` → `PickRandomly`
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
from ...entities.effect_type import EffectType


def build_summon_context(entity_id: int, visual_id: str, summon_ability: str,
                         caster_level: Optional[int], caster_mult: int, key_suffix: str = ""):
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
    # `key_suffix` : certaines abilities nomment leurs vars de stats summon avec un suffixe (ex. CultDemagogue
    # = `summonHp_2`/`summonDmg_2`/`summonArmor_2`, cf. gameconfig) — une clé absente (ex. crit du neophyte) -> 0.
    stats = UnitStats()
    for st, key in ((StatType.ATTACK, "summonDmg"), (StatType.HEALTH, "summonHp"),
                    (StatType.FIXED_ARMOR, "summonArmor"), (StatType.CRIT_CHANCE, "summonCritChance"),
                    (StatType.CRIT_DAMAGE, "summonCritDmg")):
        stats.ensure_seeded(st, sv(key + key_suffix))
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


def build_decoy_context(entity_id: int, visual_id: str = "genesSmnDecoy"):
    """`UnitContext` d'un token decoy — `SpawnUnitOptions$$IdunBattle.Entities.Behaviours.SpawnUnitOptions$$ForSteppable` = `Level(1)` +
    `CreateSpawnOptions(state,0,0,0,0)` (aucun override) : PAS de summon-scaling (contrairement à
    `build_summon_context`). Le decoy prend le kit BRUT de sa config `genesDecoy`/`genesSmnDecoy` :
    traits `Steppable`(27)+`Decoy`(1053), AUCUNE arme, AUCUNE stat de combat (config `stats` = juste
    `AbilityLevel:1`). Token inerte (`move=None`, non-ciblable)."""
    import gameconfig as GC
    from ...entities import UnitContext
    from ...entities.stats import UnitStats, StatType
    gu = GC.unit(visual_id) or {}
    stats = UnitStats()
    for st in (StatType.ATTACK, StatType.HEALTH, StatType.FIXED_ARMOR, StatType.CRIT_CHANCE,
               StatType.CRIT_DAMAGE, StatType.BLOCK_CHANCE, StatType.BLOCK_DAMAGE, StatType.EXTRA_HITS):
        stats.ensure_seeded(st, 0)
    return UnitContext(
        entity_id=entity_id, visual_id=visual_id,
        active_ability_level=1, ability_variables_multiplier=100,
        traits=list(gu.get("traits") or []),           # Steppable, Decoy (config brute)
        range=0, faction=gu.get("FactionId"),
        number_of_members=1,
        normal_profile=None, normal_profile_pierce=0,
        normal_weapon_hits=1, normal_ranged=False,
        stats=stats,
    )


def spawn_decoy(state: State, tile, caster_id: int, visual_id: str = "genesSmnDecoy") -> Optional[int]:
    """`DSLFactory$$IdunBattleLogic.Entities.DSLFactory$$Spawn(genesSmnDecoy, ForSteppable)` → `SpawnUnitBehaviour.Execute` →
    `AddUnitOperation.Execute` (MÊME socle que ScarabHive/`SpawnUnitOperation`, options DIFFÉRENTES) : pose UN
    token decoy sur `tile` (id de tuile). Options `SpawnUnitOptions$$IdunBattle.Entities.Behaviours.SpawnUnitOptions$$ForSteppable` :
      - owner = team+player du **caster** (hérité, comme `CopyOwner`) ;
      - stats = kit BRUT `genesDecoy` (level 1, PAS de `ability_var` summon-scaling) ;
      - **`ai_controlled=False`, AUCUNE on-appearance** — le token est INERTE (≠ `SpawnUnitOperation` qui force
        `ai_controlled=True` + attaque à l'apparition). Piège validator #3 : ne PAS réutiliser
        `SpawnUnitOperation.execute` tel quel.
    Renvoie l'entity id (None si `tile` None / caster introuvable). Appelé par les feuilles decoy (G4/G6/G2).
    Fondation G1 : la primitive ; les sélecteurs de tuiles (où poser) sont propres à chaque ability."""
    if tile is None:
        return None
    caster = state.get_entity(caster_id)
    coc = caster.get_component(OwnerComponent) if caster is not None else None
    if coc is None:
        return None
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=False))
    e.add_component(OwnerComponent(team=coc.team, player=coc.player))   # CopyOwner (caster)
    ctx = build_decoy_context(e.id, visual_id)
    e.add_component(StatsComponent(ctx=ctx))
    # HARDCODE (token) : le decoy n'a AUCUN HP de config -> HealthComponent nominal hp=1 pour qu'il OCCUPE la
    # tuile et soit "vivant"/tuable. hp=1 n'est PAS un seuil de dégât réel : un decoy est détruit par step
    # (crush, G1) OU par tout damage (instakill "destroyed if damaged", Decoy trait -> G2). A revoir si la RE
    # G2 révèle un HealthComponent natif spécifique.
    e.add_component(HealthComponent(hp=1, hp_max=1))
    board = state.board
    tinfo = board.by_id.get(tile) if board is not None else None
    if tinfo is not None:
        e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
    return e.id


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
                       level, mult: int, team, player, ai_controlled: bool = True,
                       key_suffix: str = "", parent_id: Optional[int] = None) -> Optional[int]:
    """Spawn UNE unité `visual_id` sur `tile` (id de tuile), stats `WithStatsFromConfig(summon_ability)` =
    `ability_var(summon_ability, summon*[key_suffix], level, mult)`, owner = team+player, `active_ability_level
    = level` (propagé → lève le GAP PileIn 2e-gen). Renvoie l'entity id (None si `tile` None). Partagé par
    GetEmRuntz/SquigHound (WithStatsFromConfig, PAS clone) et par CultDemagogue (neophyte).
    `ai_controlled` = summon auto-joué au turn-start (grots/swarms) vs unité normale jouée au tour de sa team
    (neophyte = trait Ambush+BattleFatigue, PAS Summon → `False`). `key_suffix` = suffixe des clés de stats
    (ex. `_2` pour CultDemagogue).

    `parent_id` = le CASTER (mirror `Unit_Parent_Id` emis nativement au spawn d'un summon ; ground truth
    live SupremeCommander : `Step#10 e=<summon> Unit_Parent_Id=<casterId>`). Alimente `Parent(Self)`
    (`ListenUpMaggotsEffect.CreateTargetSelector`) et `Children(caster)`. None = lien non pose."""
    if tile is None:
        return None
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=ai_controlled,
                                  parent_id=parent_id))
    e.add_component(OwnerComponent(team=team, player=player))
    ctx = build_summon_context(e.id, visual_id, summon_ability, level, mult, key_suffix=key_suffix)
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


IGNORE_BATTLE_FATIGUE = int(EffectType.IgnoreBattleFatigue)  # 1079 — vérifié par BattleFatigueAbility (behaviour.py, meme const, #158)


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
    """`SquigHound_IgnoreBattleFatigueEffect IdunBattle.Entities.Effects.Loki.SquigHound_IgnoreBattleFatigueEffect$$CreateTargetSelector` (aura de Snotflogga sur les grots amis) : si la team
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


def _materialize_owner_effect(state: State, unit_id: int, name: str, mult: int,
                              ability_level: Optional[int] = None) -> bool:
    """Matérialise UN owner-effect (par nom) sur l'unité dans `EffectsState`, PERMANENT (rem=None), comme les
    unités initiales seedées depuis capture — pour que `attacker_modifiers`/`defender_modifiers` (qui lisent
    `state.effects`) le voient. Idempotent (gate `has_effect`). Renvoie True si ajouté.

    `ability_level` = niveau de l'ability SOURCE de l'owner-effect (indexe ses variables per-niveau ; ex.
    HypersensoryAbilities.hpPct[level] = 30..50). Threadé par `_seed_ability_owner_effects` depuis
    `ctx.passive_ability_level` ; None = fallback stack level dans l'effet."""
    from ...entities.effects import EffectFactory
    from ...entities import EffectsState
    if state.effects is None:
        state.effects = EffectsState.seed({})
    if state.effects.has_effect(unit_id, name=name):
        return False                                         # déjà présent
    # effectType depuis l'enum (l'entité-effet native porte un EffectType @+0x58) : le nom d'owner-effect ==
    # nom de membre `EffectType` -> resout l'id (ex. HypersensoryAbilities_MinimalHealth=1380). None si le nom
    # n'est pas un membre (fidélité-safe ; sans ça un effet materialise a effect_type=None -> casse les
    # consommateurs qui font `int(effect_type)`, ex. filtre chainage G2).
    etype = EffectType.__members__.get(name)
    eff = EffectFactory.create({"name": name, "effectType": (int(etype) if etype is not None else None),
                                "remaining": 0},               # rem 0 -> permanent
                               ability_variables_multiplier=int(mult or 100),
                               ability_level=ability_level)
    eff.target = unit_id
    state.effects.add_effect(unit_id, eff)
    return True


def _seed_trait_owner_effects(state: State, unit_id: int, traits, mult: int) -> list:
    """`IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute (boucle TRAITS) : à la création d'unité, CHAQUE
    trait ajoute à son PORTEUR les owner-effects de `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetEffectToBeAddedToOwnerForTrait (dict `Trait..idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor +0x30). Sans ce seed, un summon SPAWNÉ n'a AUCUN effet -> ses
    traits de dégât (HeavyWeapon +25% ranged, RangedSpecialist +33% ranged, ...) ne s'appliquent PAS à ses
    attaques (gap corrigé)."""
    from ...entities.effects.factory import get_effect_to_be_added_to_owner_for_trait
    return [name for tr in (traits or [])
            for name in get_effect_to_be_added_to_owner_for_trait(tr)
            if _materialize_owner_effect(state, unit_id, name, mult)]


def _seed_derived_ability_owner_effects(state: State, unit_id: int, traits, mult: int) -> list:
    """Chemin trait -> ability DÉRIVÉE -> owner-effect posé à l'INIT de l'ability (mécanisme DISTINCT des 2
    dicts owner-effect directs). Mirror `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` (trait -> ability,
    dict Trait +0x0/+0x8) puis `<Ability>.CreateBehaviour` (DSL `AddEffect(owner)` à l'init de l'ability).

    Cas porté : trait **BigTarget** -> ability `BigTarget` (0x406) -> `IdunBattleLogic.Entities.Abilities.Active.Loki.BigTargetAbility$$CreateBehaviour` = `AddEffect(BigTarget_AdjacentEffect)` (aura -1 hit ranged aux alliés ring-1, source-side).
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


TELEPORT_STRIKE_TELEPORTING_IN = int(EffectType.TeleportStrike_TeleportingIn)  # 1035 — etat deep-strike (#158 ; 1035=effet, PAS UnitTrait.CloseCombatWeakness)


def _seed_ability_owner_effects(state: State, unit_id: int, vid: str, mult: int,
                                ability_level: Optional[int] = None) -> list:
    """`IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` (boucle ABILITIES) : pour chaque ability de
    l'unite, l'owner-effect pose par son `CreateBehaviour` a l'init (DSL `AddEffect(owner)`). Ex. passive
    `PathOfCommand` -> `PathOfCommand_ExtraDmg` (aura +Attack) ; passive `HypersensoryAbilities` ->
    `HypersensoryAbilities_MinimalHealth` (HP-floor). Abilities lues de gameconfig (active+passive).
    `ability_level` (= `ctx.passive_ability_level`) indexe les variables per-niveau de l'owner-effect posé."""
    import gameconfig as GC
    from ...entities.effects.factory import get_owner_effects_added_on_ability_init
    gu = GC.unit(vid) or {}
    abilities = list(gu.get("activeAbilities") or []) + list(gu.get("passiveAbilities") or [])
    return [name for ab in abilities
            for name in get_owner_effects_added_on_ability_init(ab)
            if _materialize_owner_effect(state, unit_id, name, mult, ability_level=ability_level)]


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
    added = _seed_ability_owner_effects(state, unit_id, vid, mult,
                                        ability_level=getattr(ctx, "passive_ability_level", None))   # PathOfCommand aura / HP-floor
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
            # mirroir du flag runtime `IdunBattle.View.Game.IdunGameViews$$IsPlayerAiControlled. TOUS les summons d'ability sont
            # ai_controlled : le scarab s'auto-dédouble (`ScarabSummon` IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour) + attaque, jamais inerte
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
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour` (auto-DÉDOUBLEMENT) : le summon s'invoque
        LUI-MÊME. Spawn `count` clones sur des tuiles LIBRES adjacentes au **CASTER** (self@0x160), owner+
        stats = `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner(caster)` (owner du caster + STATS clonées du parent).

        CopyOwner (RE IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner) copie les StatType `{0=Attack, 1=Movement, 5=Health, 16=Armor, 20}` du
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
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour` — auto-DÉDOUBLEMENT du grot (PASSIF fin-de-tour).
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
    def execute_squighound_summon(state: State, caster_id: int, target_id: int) -> list:
        """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SquigHoundSummonUnitAbility$$CreateBehaviour` (passif triggé, orksRuntherd). APRÈS une
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

    @staticmethod
    def execute_control_edict_summon(state: State, caster_id: int) -> list:
        """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$SummonMinion` (branche PROTECTOR, passif de Tan Gi'da). Apres une
        attaque NORMALE du caster (trigger `On(0x26)`), si **< maxSummons[level]** Skitarii Vanguards amis
        vivants, spawn 1 `admecSmnVanguard` sur une tuile LIBRE ADJACENTE AU **CASTER** (Tan), stats
        `WithStatsFromConfig(ControlEdict)` (`summonHp/summonDmg/summonArmor[level]`), `active_ability_level =
        casterLevel` (propage -> le Skitarii joue son tour via run_ai_control_pass). Renvoie [id] ou [].

        DIFFERENCES vs `execute_squighound_summon` (mirror natif distinct) :
          - hex libre adjacent au **CASTER** (`AdjacentTiles(caster)`), PAS a la cible ;
          - cap = `ability_var("ControlEdict","maxSummons", level)` = **PER-NIVEAU (3/4/5)**, PAS une constante ;
          - **AUCUNE on-appearance** (le Skitarii ne joue pas a l'apparition -- il agit a SON tour ; la branche
            Conqueror d'un cast ULTERIEUR le fait attaquer). Cf. verdict RE ControlEdict.
        `If(NOT AmountIsEqualOrGreater(Children INTER UnitsWithId(admecSmnVanguard), maxSummons)) -> Spawn` :
        no-op au cap (pas de remplacement). Placement natif = `First(SortTilesByUtilityForSummon(CanAddUnit(
        AdjacentTiles(caster)),7),1)` ; ici `_pick_randomly` (tri par utilite-summon = raffinement, == SquigHound)."""
        import gameconfig as GC
        from ...entities.effects.magnitude import ability_var
        caster = state.get_entity(caster_id)
        board = state.board
        if caster is None or board is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        c_ctx = csc.ctx if csc is not None else None
        if coc is None or c_ctx is None:
            return []
        consts = (GC.ability("ControlEdict") or {}).get("constants") or {}
        vid = consts.get("unitId")                        # admecSmnVanguard
        if vid is None:
            return []
        level = getattr(c_ctx, "active_ability_level", None)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        max_summons = int(ability_var("ControlEdict", "maxSummons", level) or 5)   # PER-NIVEAU (pas constante)
        # cap : `Children INTER UnitsWithId(admecSmnVanguard)` = Skitarii amis vivants (approx par team+visualId).
        n = sum(1 for e in state.entities.values()
                if (u := e.get_component(UnitComponent)) is not None and u.alive and u.visual_id == vid
                and (o := e.get_component(OwnerComponent)) is not None and o.team == coc.team)
        if n >= max_summons:                              # NOT AmountIsEqualOrGreater(count, max) False -> no-op
            return []
        tiles = _free_tiles_adjacent(state, caster_id, set())   # CanAddUnit(AdjacentTiles(CASTER))
        tile = _pick_randomly(state, tiles)               # SortTilesByUtilityForSummon+First = raffinement
        gid = _spawn_config_grot(state, vid, tile, "ControlEdict", level, mult, coc.team, coc.player)
        return [gid] if gid is not None else []

    @staticmethod
    def execute_master_of_tutelaries_screamer(state: State, owner_id: int) -> list:
        """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateSummonBehaviour` (triggered 1173,
        armee par l'effet 1197 sur Abraxas — #202-C). Spawn UN `thousSmnScreamer` :

          RemoveEffect(EntitiesWithAnyEffect(@0x80, 0x425=1061 GeminaeSuperia_JustSummonedEffect))
          & Spawn( owner@0x148,
                   PickRandomly( TilesUnitCanAttackFrom( CanAddUnit(AdjacentTiles(owner@0x148)),
                                                         owner, unitId_2="thousSmnScreamer" )
                                 .Otherwise(possible), 1 ),
                   unitId_2, WithStatsFromConfig2(config 1096) + onAppearance=PerformAIAttackFromCurrentPosition )

        - possible = tuiles LIBRES adjacentes au PORTEUR (== `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$GetPossibleSummonTiles`) ;
        - preferred = celles d'ou le Screamer (MELEE, Power 3 hits) peut attaquer = >=1 ennemi VIVANT
          adjacent (porte d'elevation `is_adjacent`) (== `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$GetPreferredSummonTiles` :
          `TilesUnitCanAttackFrom(...).Otherwise(possible)`) ;
        - stats `WithStatsFromConfig2(config 1096)` = summonHp/summonDmg de MasterOfTheTutelaries au
          niveau ACTIF du porteur (la variante `2` derive le niveau de l'ability-state propage par
          l'effet 1197 = celui de l'active 1096 — meme valeur que le Horror) ;
        - le RemoveEffect(1061) préalable est mirrore par consommation des instances 1061 (marqueur
          `GeminaeSuperia_JustSummonedEffect`) — NO-OP offline tant qu'aucun poseur de 1061 n'est
          porte (aucun AddEffect(1061) dans ce kit ; poseur natif hors perimetre, residu case-202 §8).
        L'ON-APPEARANCE (`PerformAIAttackFromCurrentPosition`) est execute par l'APPELANT (le trigger),
        comme SquigHound/ControlEdict. Renvoie [id] ou []."""
        import gameconfig as GC
        caster = state.get_entity(owner_id)
        board = state.board
        if caster is None or board is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        c_ctx = csc.ctx if csc is not None else None
        if coc is None or c_ctx is None:
            return []
        consts = (GC.ability("MasterOfTheTutelaries") or {}).get("constants") or {}
        vid = consts.get("unitId_2")                      # thousSmnScreamer (GetStringConstant(config, 4))
        if vid is None:
            return []
        # RemoveEffect(1061) sur tous les porteurs — mirror structurel, no-op offline (cf. docstring).
        eff = getattr(state, "effects", None)
        if eff is not None:
            for _uid, _effs in eff.by_unit.items():
                for _e in _effs:
                    if not _e.consumed and _e.effect_type == 1061:
                        _e.consumed = True
        possible = _free_tiles_adjacent(state, owner_id, set())  # CanAddUnit(AdjacentTiles(owner))
        # TilesUnitCanAttackFrom(possible, owner, "thousSmnScreamer") : Screamer = MELEE -> tuiles avec
        # >=1 ennemi VIVANT hex-adjacent (porte d'elevation |dElev|<2, `is_adjacent` maison).
        from engine.battle_query import is_adjacent
        elev = {}
        epos = []
        for eid2, e2 in state.entities.items():
            oc2 = e2.get_component(OwnerComponent)
            uc2 = e2.get_component(UnitComponent)
            pc2 = e2.get_component(PositionComponent)
            if oc2 is None or pc2 is None or oc2.team == coc.team:
                continue
            if uc2 is not None and not uc2.alive:
                continue
            epos.append((pc2.col, pc2.row))
        if board is not None:
            elev = {(t["col"], t["row"]): t.get("elevation") for t in board.by_id.values()
                    if t.get("elevation") is not None}
        def _can_attack_from(tid) -> bool:
            ti = board.by_id.get(tid)
            if ti is None:
                return False
            return any(is_adjacent((ti["col"], ti["row"]), p, elev) for p in epos)
        preferred = [t for t in possible if _can_attack_from(t)]
        sel = preferred if preferred else possible        # .Otherwise(possible)
        tile = _pick_randomly(state, sel)                 # PickRandomly(sel, 1)
        level = getattr(c_ctx, "active_ability_level", None)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        # MESURE LIVE (diag 202c, runner 183) : Screamer MaxHealth 4487 = summonHp_2[50] x 180%
        # (2493*1.8) -> les stats du Screamer = variables suffixees `_2` (summonHp_2/summonDmg_2,
        # meme convention que CultDemagogue), PAS summonHp/summonDmg (le Horror).
        gid = _spawn_config_grot(state, vid, tile, "MasterOfTheTutelaries", level, mult,
                                 coc.team, coc.player, key_suffix="_2")
        return [gid] if gid is not None else []
