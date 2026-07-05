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

if TYPE_CHECKING:
    from ..state import State

STUNNED = 0x48a          # 1162 EffectType.Stunned (effet COMPOSITE → enfants 1165/1166/1167)
TAUNTED = 0x1b           # 27 EffectType.Taunted_OnlySpecificTargets (COMPOSITE → 25/26/1237 ; bond)
PINNED = 0x429           # 1065 EffectType.Pinned (UI « Suppressed ») — stat-mod Movement


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
        state, summon_id, target_id, int(ctx.stat(StatType.ATTACK)), pierce, hits=hits, spread_pct=20)


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
                state, caster_id, target_id, bmin, bmax, pierce, hits)
            # [AddEffect] Stunned 1162, durée = TurnsFromRounds(1 round) :
            AddEffectOperation.execute(state, source=caster_id, target=target_id,
                                       effect_type=STUNNED, name="Stunned",
                                       duration_override=turns_from_rounds(1))
        # [push/kill/move] PushUnit(target) & KillDeadUnits & MoveUnit(caster) : déplacements/positions.
        # TODO (tranche déplacement). BigTarget cible => push no-op (cf. RE tyranTyrantGuard).
        return {"attack": atk}


class ScarabSummonAbility(ActiveAbility):
    """`ScarabSummonAbility.ExecuteBehaviour` @181205290 (id 1007 = ScarabHive, necroSpyder).

    Séquence native :
        Spawn(visualId = constants["unitId"] = necroSmnSwarm,
              tile = PickRandomly(CanAddUnit(AdjacentTiles(target@0x160))),   # libre, adjacent CIBLE
              owner = SpawnUnitOptions.CopyOwner(caster),                     # team ET player du caster
              onAppearance = PerformAIAttack)                                 # attaque immédiate
        × COUNT (2, arg du .ctor AActiveAbility)
    Stats du summon = `ability_var(ScarabHive, summonHp/summonDmg/…, casterActiveAbilityLevel, mult)`.
    À l'apparition chaque summon attaque la cible avec le profil `unitDamageProfile` (Piercing) en
    override de son arme Energy (i2). VALIDÉ live : 2× necroSmnSwarm team/player du caster, hp/attack
    bit-exact (cf. test_summon_spawn_live) ; wiring message + on-appearance (cf. test_summon_trigger_live)."""
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


def _adjacent_to_both(state: "State", caster_id: int, target_id: int) -> list[int]:
    """Splash CrushingClaws : ennemis VIVANTS du caster adjacents (hex) **À LA FOIS** au caster ET à la
    cible, hors cible. Mirror `GetAdjacentDamageTargetsUnits` @1811cdad0 =
    `AdjacentEnemies(actor) & (AdjacentFriends(target) - target)` (les amis de la cible = ennemis du
    caster ⇒ ennemis adjacents aux deux). Requiert `state.board` (evenq). ⚠ exclusion
    `UnitsWithoutTrait(0xd=13)` NON portée (mapping de l'enum trait 13 inconnu offline) → TODO ; sans
    board → [] (no-op fidèle)."""
    board = getattr(state, "board", None)
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
            state, caster_id, target_id, bmin, bmax, pierce, hits)
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
                state, caster_id, sid, bmin2, bmax2, pierce2, hits2)
            splash.append({"target": sid, "attack": satk})
        return {"ability": "CrushingClaws", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash}


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
                state, caster_id, target_id, bmin, bmax, pierce, hits)
            # [AddEffect] Stunned 1162, durée = TurnsFromRounds(nrOfRounds=1) :
            AddEffectOperation.execute(state, source=caster_id, target=target_id,
                                       effect_type=STUNNED, name="Stunned",
                                       duration_override=turns_from_rounds(1))
        return {"attack": atk}
