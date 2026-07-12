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
from ..operations.heal import HealUnitOperation
from ..operations.spawn import SpawnUnitOperation
from ..components import StatsComponent, OwnerComponent, PositionComponent, UnitComponent
from ...entities.stats import StatType

if TYPE_CHECKING:
    from ..state import State

STUNNED = 0x48a          # 1162 EffectType.Stunned (effet COMPOSITE → enfants 1165/1166/1167)
TAUNTED = 0x1b           # 27 EffectType.Taunted_OnlySpecificTargets (COMPOSITE → 25/26/1237 ; bond)
PINNED = 0x429           # 1065 EffectType.Pinned (UI « Suppressed ») — stat-mod Movement
VALKYRIE_STRIKE = 0x3fe  # 1022 EffectType.ValkyrieStrike_Effect (airstrike DIFFÉRÉ, fire au tour suivant)


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

    Séquence native (`&` = op_BitwiseAnd) :
        AttackWithAttackDamage(Nearest enemy, 1x Power)        # [DAMAGE param-ability — TODO]
      & AddEffect(0x48a Stunned, source=casterStateRef, TurnsFromRounds(1))   # ← PORTÉ ici (vecteur attaque)
      & PushUnit(target, 1 hex)                                # [déplacement — TODO ; no-op si BigTarget]
      & KillDeadUnits & MoveUnit(caster -> hex libéré)         # [déplacement — TODO]
    VALIDÉ live : pose Stunned(1162, rem=1) + enfants 1165/1166/1167 sur la cible (cf. test_effect_stun_live)."""
    __slots__ = ()
    ABILITY_TYPE = 1043

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        atk = None
        if target_id is not None:
            # [attaque] AttackWithAttackDamage — dégât d'ABILITY (minDmg/maxDmg config[level], profile
            # Power adjacent, nrOfHits=1). Mute les PV cible (skip si rng non calé : replay effet-seul).
            bmin, bmax, pierce, hits = ability_attack_params(
                state, caster_id, "ThunderousAssault", "Power", ranged=False)
            atk = AttackDamageOperation.execute_ability_attack(
                state, caster_id, target_id, bmin, bmax, pierce, hits,
                damage_profile="Power", is_melee=True)
            # [AddEffect] Stunned 1162, durée = TurnsFromRounds(1 round) :
            AddEffectOperation.execute(state, source=caster_id, target=target_id,
                                       effect_type=STUNNED, name="Stunned",
                                       duration_override=turns_from_rounds(1))
        # [push/kill/move] PushUnit(target) & KillDeadUnits & MoveUnit(caster) : déplacements/positions.
        # TODO (tranche déplacement). BigTarget cible => push no-op (cf. RE tyranTyrantGuard).
        return {"attack": atk}


class ArmoriumCherubAbility(ActiveAbility):
    """`ArmoriumCherubAbility.ExecuteBehaviour` (id 1014, adeptRetributor «Vindicta»).

    Actif RANGED : `AttackWithAttackDamage(target, MinMaxDamage(minDmg/maxDmg[level]), Flame, nrOfHits=const
    0x2f=4)` (range 2). Profil Flame (`OnFire`) → POSE du feu sur la tuile-cible via le vecteur after-hit
    d'ability (`execute_ability_attack` → `_on_fire_damage_ability`, #136). i2 « Using Armorium Cherub does
    not end Vindicta's turn » = turn-flow (ne consomme pas le tour) — NON modélisé ici (concern turn-order).

    En + : le passif `FireOfAbsolution` réagit à CETTE attaque ranged (splash 3x Flame sur les ennemis
    adjacents à la cible + 30% ignite/hex) — mirroir du natif où le passif se déclenche sur toute attaque
    ranged de l'unité. Cf. `_fire_of_absolution_after_attack`."""
    __slots__ = ()
    ABILITY_TYPE = 1014
    ABILITY_ID = "ArmoriumCherub"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # [attaque] 4x Flame (minDmg/maxDmg[level], range 2, nrOfHits=const 0x2f=4). Feu posé sur la cible (#136).
        bmin, bmax, pierce, hits = ability_attack_params(
            state, caster_id, self.ABILITY_ID, "Flame", ranged=True)
        main = AttackDamageOperation.execute_ability_attack(
            state, caster_id, target_id, bmin, bmax, pierce, hits,
            damage_profile="Flame", is_melee=False)
        # [passif] FireOfAbsolution sur cette attaque RANGED : splash 3x Flame adjacents + 30% ignite/hex.
        from ..operations.triggers import _fire_of_absolution_after_attack
        passive = _fire_of_absolution_after_attack(state, caster_id, target_id, ranged=True)
        return {"ability": "ArmoriumCherub", "caster": caster_id, "target": target_id,
                "main_attack": main, "fire_of_absolution": passive}


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
    ABILITY_TYPE = 1007
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
    ABILITY_TYPE = 1047
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
    hex LIBRE adjacent au caster **ET** adjacent à un ennemi (`GetSpawnTileSelector @1811e26b0`), stats
    `WithStatsFromConfig(GetEmRuntz)` (4802 PV @lvl65/mult100 ; 7312 @lvl50/mult200). Chaque grot porte
    `active_ability_level = casterLevel` → **lève le GAP PileIn** (les grots pourront se dédoubler avec des
    stats correctes). Cf. `SpawnUnitOperation.execute_getemruntz`.

    On-appearance : `PerformAIAttackFromCurrentPosition` (le grot attaque SANS bouger) — ici approximé par une
    attaque sur l'ennemi le plus proche (rng requis) ; le Taunt(1t) des ennemis touchés
    (`TauntWithNewChildrenWhoDidDamage @1811e27a0`) = FLAGGÉ non porté (secondaire)."""
    __slots__ = ()
    ABILITY_TYPE = 1045

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        spawned = SpawnUnitOperation.execute_getemruntz(state, caster_id)
        attacks, taunts = [], []
        if state.rng is not None:                # on-appearance PerformAIAttackFromCurrentPosition
            for sid in spawned:
                tgt = _nearest_enemy(state, sid)
                if tgt is None:
                    continue
                r = AttackDamageOperation.execute(state, sid, tgt)
                if r is None:
                    continue
                attacks.append({"summon": sid, "target": tgt, "total": r.get("total")})
                # [Taunt] `TauntWithNewChildrenWhoDidDamage @1811e27a0` : l'ennemi attaqué par un NOUVEAU grot
                # qui a fait du dégât (LastUnitAttackedBy & TotalAttacksMade>0 & vivant) est Taunted 1 round
                # (`AddBondEffect(0x1b=27)` — COMPOSITE 25/26/1237). Bond grot↔ennemi = ciblage IA (playbook).
                te = state.get_entity(tgt)
                tuc = te.get_component(UnitComponent) if te is not None else None
                if tuc is not None and tuc.alive:
                    AddEffectOperation.execute(state, source=sid, target=tgt, effect_type=TAUNTED,
                                               name="Taunted_OnlySpecificTargets",
                                               duration_override=turns_from_rounds(1))
                    taunts.append(tgt)
        return {"summon": "orksGrot", "spawned": spawned, "attacks": attacks, "taunted": taunts,
                "getemruntz": True}


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


def _adjacent_tyranid_allies(state: "State", self_id: int) -> list[int]:
    """Volet ADJACENT de `SpiritLeechAbility.GetHealTargets @18120a1e0` :
    `UnitsFromFaction(Friends(self, AdjacentUnits(self, range=1)), faction 0xc=12=Tyranids)` = amis
    (MEME team) VIVANTS de `self_id`, ADJACENTS (hex range 1, `board.neighbours`), de faction Tyranids.
    (`self` est ajoute SEPAREMENT par l'appelant via `op_Addition(Self, ...)`, sans gate faction.)
    Reutilise `_faction` (resolution FactionId gameconfig deja portee cote decision, PAS de fork).
    Sans board -> [] (no-op fidele). Ordre deterministe (tie-break id)."""
    from ...ai.action_generators import _faction
    board = state.board
    e = state.get_entity(self_id)
    if board is None or e is None:
        return []
    pc = e.get_component(PositionComponent)
    oc = e.get_component(OwnerComponent)
    if pc is None or oc is None:
        return []
    tile = board.id_at(pc.col, pc.row)
    if tile is None:
        return []
    neigh = set(board.neighbours(tile))
    out: list[int] = []
    for eid, o in state.entities.items():
        if eid == self_id:
            continue
        ooc = o.get_component(OwnerComponent)
        ouc = o.get_component(UnitComponent)
        opc = o.get_component(PositionComponent)
        if ooc is None or opc is None or ooc.team != oc.team:     # amis (meme team) uniquement
            continue
        if ouc is not None and not ouc.alive:                     # vivants
            continue
        if board.id_at(opc.col, opc.row) not in neigh:            # adjacent (hex range 1)
            continue
        if ouc is None or _faction(ouc.visual_id) != "Tyranids":  # faction 0xc=12=Tyranids
            continue
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
    1 hex) est différé (cf. ThunderousAssault) ; l'exclusion **trait 0xd** du splash est différée (enum
    inconnu). Effets posés sur la cible SANS gate IsAlive (comme le natif) ; splash gated alive."""
    __slots__ = ()
    ABILITY_TYPE = 1105
    ABILITY_ID = "CrushingClaws"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # [attaque principale] 2× Piercing (minDmg/maxDmg[level], nrOfHits=const 0x2f=2). Mute les PV cible.
        bmin, bmax, pierce, hits = ability_attack_params(
            state, caster_id, self.ABILITY_ID, "Piercing", ranged=False)
        main = AttackDamageOperation.execute_ability_attack(
            state, caster_id, target_id, bmin, bmax, pierce, hits,
            damage_profile="Piercing", is_melee=True)
        # [Taunt] AddBondEffect(27, TurnsFromRounds(1)) — COMPOSITE (enfants 25/26/1237 same-turns).
        # Bond cible→tauntant (ciblage IA) = concern playbook (TODO) ; source=caster capture la direction.
        AddEffectOperation.execute(state, source=caster_id, target=target_id, effect_type=TAUNTED,
                                   name="Taunted_OnlySpecificTargets",
                                   duration_override=turns_from_rounds(1))
        # [Suppressed cible] AddEffect(1065 Pinned) — durée = DefaultAmountOfRounds(1065)=1.
        AddEffectOperation.execute(state, source=caster_id, target=target_id, effect_type=PINNED,
                                   name="Pinned")
        # [splash] ennemis adjacents au caster ET à la cible (recul + Suppressed + 1× Physique).
        bmin2, bmax2, pierce2, hits2 = ability_attack_params(
            state, caster_id, self.ABILITY_ID, "Physical", ranged=False,
            min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2")
        splash: list[dict] = []
        for sid in _adjacent_to_both(state, caster_id, target_id):
            # [push] PushUnit(actor, s) recul 1 hex — TODO (tranche déplacement).
            se = state.get_entity(sid)
            uc = se.get_component(UnitComponent) if se is not None else None
            if uc is None or uc.alive:                            # If(alive) AddEffect(Pinned) AVANT l'attaque
                AddEffectOperation.execute(state, source=caster_id, target=sid, effect_type=PINNED,
                                           name="Pinned")
            satk = AttackDamageOperation.execute_ability_attack(
                state, caster_id, sid, bmin2, bmax2, pierce2, hits2,
                damage_profile="Physical", is_melee=True)
            splash.append({"target": sid, "attack": satk})
        return {"ability": "CrushingClaws", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash}


class SpiritLeechAbility(ActiveAbility):
    """`SpiritLeechAbility.ExecuteBehaviour @181209900` (id 1104, tyranNeurothrope).

    Sequence native (`&`/`+` = compositions de behaviour) :
        AttackWithAbilityDamage(target, GetAttackDamage(combat), profile=Psychic, nrOfHits=const 0x2f=1)  # attaque
      & AddEffect(0x429=1065 Pinned, target)                                     # « Suppressed » cible
      & Heal(Friends(self) + AdjacentUnits(self,1) faction Tyranids,
             PercentageOf(LastAttackDamageMade, hpToHealPct=ConfigVar 0x4b=60%))  # lifesteal  [DIFFERE, tache #94]

    `GetAttackDamage @181209dd0` COMBAT (param_3=0) = `RandomAmount(minDmg, maxDmg)` [+ extraDmg (ConfigVar 8)
    SI la cible est DEJA Pinned/Suppressed (0x429) : `ConditionalAmount(NOT HasEffect(Pinned), base, base+extraDmg)`].
    Profil Psychic, ranged (range 3, nrOfHits=1). ⚠ COMBAT = CONFIG-based (config-avg×mult180 = 2593), != la
    PREDICTION Attack-based (~2670, slot 0x27 ; cf. playbook/prediction.py `_PREDICT_VIA_NORMAL_ATTACK`) —
    DIVERGENCE NATIVE preview/combat (verdict #92).

    Porte : attaque (config + bonus Suppressed) + Pinned cible. Le LIFESTEAL (3e behaviour) est DIFFERE
    (tache #94 : necessite un HealOperation combat)."""
    __slots__ = ()
    ABILITY_TYPE = 1104
    ABILITY_ID = "SpiritLeech"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # [attaque] RandomAmount(minDmg/maxDmg[level], profil Psychic, nrOfHits=1). Mute les PV cible.
        bmin, bmax, pierce, hits = ability_attack_params(
            state, caster_id, self.ABILITY_ID, "Psychic", ranged=True)
        # [bonus Suppressed] + extraDmg (ConfigVar 8) SI la cible est DEJA Pinned (0x429) au moment de l'attaque
        # (ConditionalAmount(NOT HasEffect(Pinned), base, base+extraDmg)) : flat sur les 2 bornes, AVANT le tirage.
        suppressed = state.effects is not None and state.effects.has_effect(target_id, effect_type=PINNED)
        if suppressed:
            from ...entities.effects.magnitude import ability_var
            sc = state.get_entity(caster_id)
            sc = sc.get_component(StatsComponent) if sc is not None else None
            ctx = sc.ctx if sc is not None else None
            level = ctx.active_ability_level if ctx is not None else 0
            mult = ctx.ability_variables_multiplier if ctx is not None else 100
            extra = int(ability_var(self.ABILITY_ID, "extraDmg", level, multiplier_pct=mult) or 0)
            bmin += extra
            bmax += extra
        main = AttackDamageOperation.execute_ability_attack(
            state, caster_id, target_id, bmin, bmax, pierce, hits,
            damage_profile="Psychic", is_melee=False)
        # [Suppressed cible] AddEffect(1065 Pinned) — duree = DefaultAmountOfRounds(1065)=1.
        AddEffectOperation.execute(state, source=caster_id, target=target_id, effect_type=PINNED,
                                   name="Pinned")
        # [lifesteal] Heal(GetHealTargets, GetHealAmountForExecution) — porte via HealUnitOperation (#94).
        #   cibles `GetHealTargets @18120a1e0` = op_Addition(Self, UnitsFromFaction(Friends(Self,
        #     AdjacentUnits(Self,1)), faction 0xc=12=Tyranids)) = SELF + amis Tyranids adjacents (range 1).
        #   montant `GetHealAmountForExecution @181209f00` = PercentageOf(LastAttackDamageMade,
        #     ConfigVar 0x4b=hpToHealPct) = trunc(dmg x hpToHealPct/100). hpToHealPct HORS
        #     variablesAffectedByRarityBonus -> valeur brute par niveau (multiplier 100), [40..60].
        # LastAttackDamageMade approxime par le degat SANTE de l'attaque (main["total"]) — point de
        # validation live. No-op si l'attaque n'a pas eu lieu (rng non cale : replay effet-seul).
        heals: list[dict] = []
        heal_amount = 0
        if main is not None:
            from ...entities.effects.magnitude import ability_var
            dmg = int(main.get("total") or 0)
            hsc = state.get_entity(caster_id)
            hsc = hsc.get_component(StatsComponent) if hsc is not None else None
            hctx = hsc.ctx if hsc is not None else None
            hlvl = hctx.active_ability_level if hctx is not None else 0
            pct = int(ability_var(self.ABILITY_ID, "hpToHealPct", hlvl, multiplier_pct=100) or 0)
            heal_amount = int(dmg * pct / 100)                    # PercentageOf = troncature Fix64
            if heal_amount > 0:
                for t in [caster_id] + _adjacent_tyranid_allies(state, caster_id):
                    healed = HealUnitOperation.execute(state, t, heal_amount, source_id=caster_id)
                    heals.append({"target": t, "healed": healed})
        return {"ability": "SpiritLeech", "caster": caster_id, "target": target_id,
                "main_attack": main, "suppressed_bonus": suppressed,
                "heal_amount": heal_amount, "heals": heals}


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
    ABILITY_TYPE = 1018

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
    """`PlasmaGrenadeAbility.ExecuteBehaviour` @1811f99e0 (id 1098, eldarSmnGuardian).

    Séquence native : `AttackWithAttackDamage(actor, target, MinMaxDamage, Plasma, nrOfHits=2)` +
    `Foreach(splash = Enemies(caster, AdjacentUnits(target))) AttackWithAttackDamage(actor, s, MÊME
    MinMaxDamage, Plasma, nrOfHits_2=1)`. Splash = ennemis adjacents (hex) à la CIBLE (`_adjacent_enemies_of`),
    plage de dégât PARTAGÉE (seul le nb de hits change). Ranged (range 2)."""
    __slots__ = ()
    ABILITY_TYPE = 1098
    ABILITY_ID = "PlasmaGrenade"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        splash = _adjacent_enemies_of(state, caster_id, target_id)
        return {"ability": "PlasmaGrenade", "caster": caster_id, "target": target_id,
                **_splash_ability_behaviour(state, caster_id, target_id, self.ABILITY_ID,
                                            "Plasma", ranged=True, splash_set=splash)}


class StikkbombAbility(ActiveAbility):
    """`StikkbombAbility.ExecuteBehaviour` @18120c180 (id 1051, orksOrkBoys).

    Séquence native : `AttackWithAttackDamage(actor, target, MinMaxDamage, Blast, nrOfHits=2)` +
    `AtomicGroup(Foreach(splash = AdjacentUnits(target), team-param 3 → ennemis du caster)
    AttackWithAttackDamage(actor, s, MÊME MinMaxDamage, Blast, nrOfHits_2=1))` (l'`AtomicGroup` = no-op
    offline). Splash = `_adjacent_enemies_of`, plage PARTAGÉE. Profil Blast, ranged (range 2)."""
    __slots__ = ()
    ABILITY_TYPE = 1051
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
    ABILITY_TYPE = 1078
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
    ABILITY_TYPE = 1065
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
    ABILITY_TYPE = 1206

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
