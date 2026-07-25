"""#149 slice-19 : EnvFireTile DoT (feu de tuile, `Active.Loki`) MIGRATION vers l'arbre DSL
`env_fire_tile_tree()` (mirror 1:1 de la FEUILLE de `IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour`).

Feuille native = factory `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` = DEGAT DIRECT (DISTINCTE de
`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` = Psyker/ThunderousAssault) :
    AttackWithAbilityDamage( Tiles(@0x180),
                             PercentageOf( StatAmount(@0x180, Health=5, Max=2), ConfigConst(fireDmgPct) ),
                             Direct(Nullable(3)), source = AbilityOrEffect(Fire=5) )
= base 20% PV MAX percee par PiercingRatio(Flame)=25%, l'armure absorbant le non-perce ; AUCUN
crit/block/spread/after-hit. Le port route via `AttackDamageOperation.execute_direct`.

REPLAY-DIFF (comme test_on_fire_damage) : sur DEUX etats INDEPENDANTS issus de la MEME capture LIVE, on
confronte la NOUVELLE feuille (arbre DSL -> `execute_direct`) a une COPIE VERBATIM de l'ANCIEN corps
imperatif de `FireTileDoT.execute_behaviour` (avant slice-19). Property-based : sur TOUTES les unites de la
bataille (hp_max + armure reels) -> le DoT DIRECT est BIT-EXACT unite par unite. La seule difference de
principe (base = Fix64 `PercentageOf` vs `round(float)`) est INERTE pour fireDmgPct=20 (PVmax/5 ne tombe
jamais sur .5). Lit l'etat LIVE. ASCII-only. NON committe (tests confront live, hors depot)."""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.components import HealthComponent, StatsComponent, UnitComponent
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.triggers.loki import env_fire_tile_tree, FIRE_PROFILE, FIRE_DMG_PCT_KEY
from engine.runner.abilities.behaviours import entities_from_state
from engine.dsl.effects import ExecutionContext
from engine.entities.stats import StatType
from engine.entities.pathfinding.board import Board


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _alive(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.alive if uc is not None else True


def _ref_dot(state, uid, pct):
    """Copie VERBATIM de l'ANCIEN corps de `FireTileDoT.execute_behaviour` (avant slice-19), read-only
    (calcule le DoT sans muter). ORACLE du replay-diff : base = round(float(PVmax*pct/100)) percee par
    Flame.PiercingRatio + armure (`apply_pierce_and_modifiers` mods=None ; PAS de crit/block/spread)."""
    import gameconfig as GC
    from engine.services.damage_prediction import apply_pierce_and_modifiers
    e = state.get_entity(uid)
    thc = e.get_component(HealthComponent) if e is not None else None
    if thc is None or thc.hp is None or thc.hp_max is None:
        return None
    base = round(int(thc.hp_max) * int(pct) / 100)
    pierce = int((GC.damage_profile("Flame") or {}).get("PiercingRatio") or 0)
    tsc = e.get_component(StatsComponent)
    armor = int(tsc.ctx.stat(StatType.FIXED_ARMOR)) if tsc is not None else 0
    dmg = int(round(apply_pierce_and_modifiers(base, pierce_pct=pierce, armor=armor, mods=None)))
    return dmg if dmg > 0 else None


def _new_dot(state, source_id, uid, pct):
    """NOUVELLE feuille : arbre DSL `env_fire_tile_tree` -> `execute_direct`. Renvoie (dmg, hp_before,
    hp_after) de l'attaque emise, ou (None, None, None) si aucun degat (execute_direct -> None)."""
    ectx = ExecutionContext(state=state, rng=state.rng)
    env_fire_tile_tree(int(pct), FIRE_PROFILE).execute(
        entities_from_state(state, source_id, uid), ectx)
    hit = next((p for n, p in ectx.emitted if n == "AttackWithAbilityDamage"), None)
    atk = (hit or {}).get("attack")
    if not atk:
        return None, None, None
    return atk.get("total"), atk.get("hp_before"), atk.get("hp_after")


def test_env_fire_tile_dot_migration_matches_imperative(live_session, rpc, build_runner):
    """La NOUVELLE feuille `env_fire_tile_tree` (mode DIRECT -> `execute_direct`) reproduit l'ANCIEN corps
    imperatif de `FireTileDoT` BIT-EXACT sur TOUTES les unites (DoT + PV apres), sur DEUX etats INDEPENDANTS
    issus de la MEME capture LIVE (RNG-free : degat DIRECT deterministe)."""
    rid = build_runner("777")["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not _ok(dv):
        pytest.skip("decisionView KO")

    import gameconfig as GC
    pct = GC.global_value(FIRE_DMG_PCT_KEY)
    if not pct:
        pytest.skip("fireDmgPct absent du gameconfig")

    board = Board(bg["tiles"], adjacency="native_sym") if isinstance(bg, dict) and bg.get("tiles") else None
    st_new = load_state(dv, ob, snap, board=board)
    st_ref = load_state(dv, ob, snap, board=board)

    # source = 1re entite (attribution de mort seule ; les cibles saines ne meurent pas -> source indifferente).
    ids = [eid for eid in st_new.entities if _alive(st_new, eid)
           and st_new.get_entity(eid).get_component(HealthComponent) is not None
           and st_new.get_entity(eid).get_component(StatsComponent) is not None]
    if not ids:
        pytest.skip("aucune unite vivante avec Health+Stats offline")
    source_id = ids[0]

    confronted = 0
    diffs = []
    for uid in ids:
        dmg_ref = _ref_dot(st_ref, uid, pct)
        dmg_new, hp_before, hp_after = _new_dot(st_new, source_id, uid, pct)
        if dmg_ref is None and dmg_new is None:
            continue                                      # DoT nul des deux cotes (unite sans PV/percage) -> skip
        confronted += 1
        if dmg_new != dmg_ref:
            diffs.append(f"u{uid}: new={dmg_new} ref={dmg_ref}")
            continue
        # mutation identique cote NOUVEAU (execute_direct a bien retire dmg des PV de la cible)
        if hp_before is not None and hp_after != max(0, hp_before - dmg_new):
            diffs.append(f"u{uid}: hp {hp_before}->{hp_after} != {max(0, hp_before - dmg_new)}")

    print(f"\n[ENVFIRE migration] pct={pct} source={source_id} confronted={confronted}/{len(ids)}")
    if diffs:
        print("[ENVFIRE migration] DIFFS: " + " | ".join(diffs[:12]))
    assert confronted > 0, "aucune unite confrontee (DoT nul partout) -> setup non exerce"
    assert not diffs, f"{len(diffs)} divergence(s) DSL vs imperatif: {diffs[:12]}"
