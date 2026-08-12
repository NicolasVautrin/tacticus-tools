"""#149 slice-14 : FireOfAbsolution (passif adeptRetributor «Vindicta») MIGRATION vers l'arbre DSL
`fire_of_absolution_tree()` (mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour`, RE decompile).

Arbre natif (`&` = op_BitwiseAnd, gauche->droite) :
    Inform(0xb3, EntityId(target))
  & AttackWithAttackDamage(caster, AdjacentUnits(target,0,3) − caster − target, Direct(dmg=var0xb), Flame, hits=3)
  & Maybe(SetOnFire, AdjacentTiles(target), chance=30)
Le passif fire sur toute attaque RANGED de Vindicta. On confronte le NOUVEAU `_fire_of_absolution_after_attack`
(qui DELEGUE a l'arbre : Inform no-op + splash `AttackWithAbilityDamage(multi)` + `Foreach(AdjacentTiles,
Maybe(30, SetOnFire))`) a une COPIE de reference de l'ANCIEN corps hybride imperatif (selecteur DSL + boucle
`execute_ability_attack` + boucle ignite `next_bool`/`AddEffect`). REPLAY-DIFF sur DEUX etats INDEPENDANTS
issus de la MEME capture LIVE, seedes IDENTIQUEMENT -> meme splash (set + per-coup) + memes tuiles ignitees =
BIT-EXACT (meme Operations, meme ordre splash->ignite, meme `state.rng`).

Caster = adeptRetributor «Vindicta» (BUILDABLE, porte le passif FireOfAbsolution). Cible ENNEMIE choisie via
le SELECTEUR DE SPLASH lui-meme (>=1 occupant non-ami adjacent) -> splash NON VIDE = chemin exerce. Lit l'etat
LIVE. ASCII-only. NON committe (tests confront live, hors depot).
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent, OwnerComponent, UnitComponent, PositionComponent
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.operations.triggers.loki import _fire_of_absolution_after_attack
# #951 : la chance d ignition est LUE du gameconfig (GetNumberConstant(chance)), elle
# n est plus une constante figee -- le temoin imperatif ci-dessous lit donc la MEME source.
from engine.runner.operations.triggers.loki import FIRE_TILE, fire_of_absolution_ignite_chance
from engine.runner.abilities.base import ability_attack_params
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.entities.selectors.accessors import Target, TargetTile
from engine.entities.selectors.tiles import Caster
from engine.entities.selectors.units import AdjacentUnits, Alive, Sub
from engine.entities.pathfinding.board import Board

CASTER_VIS = "adeptRetributor"              # «Vindicta» : porte FireOfAbsolution (passif)
BUILD = ["--roster", "1", "--p-units", CASTER_VIS,
         "--a-units", "necroWarden,necroDestroyer,necroSpyder,necroOverlord"]   # ennemis clusterises -> splash


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _team(state, eid):
    e = state.get_entity(eid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _alive(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.alive if uc is not None else True


def _visual(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.visual_id if uc is not None else None


def _splash_selector():
    """Selecteur de splash EXACT (mirror natif `AdjacentUnits(target) − caster − target`, position-domain,
    board-independant) — sert AUSSI a PICKER une cible avec splash non vide."""
    return Alive(Sub(Sub(AdjacentUnits(TargetTile()), Caster()), Target()))


def _splash_map(passive):
    """{splash_target -> per_hit} depuis la liste retournee par _fire_of_absolution_after_attack."""
    out = {}
    for p in (passive or []):
        for s in (p.get("splash") or []):
            out[s["target"]] = (s.get("attack") or {}).get("per_hit")
    return out


def _ignited(passive):
    out = set()
    for p in (passive or []):
        out |= set(p.get("ignited_tiles") or [])
    return out


def _fire_of_absolution_imperative_ref(state, attacker_id, target_id, ranged):
    """Copie VERBATIM de l'ANCIEN corps hybride de `_fire_of_absolution_after_attack` (AVANT slice-14) :
    splash via le SELECTEUR DSL + boucle `execute_ability_attack` + boucle ignite `next_bool`/`AddEffect`.
    ORACLE du replay-diff (independant du code migre : ne passe PAS par l'arbre)."""
    if not ranged or state.board is None or state.effects is None or state.rng is None:
        return []
    import gameconfig as GC
    e = state.get_entity(attacker_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or "FireOfAbsolution" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
        return []
    dmg, _dmg_max, pierce, hits = ability_attack_params(
        state, attacker_id, "FireOfAbsolution", "Flame", ranged=True, min_key="dmg", max_key="dmg")
    _ents = entities_from_state(state, attacker_id, target_id)
    _splash_ids = sorted(u.get("id") for u in _splash_selector().evaluate(_ents) if u.get("id") is not None)
    splash = []
    for sid in _splash_ids:
        satk = AttackDamageOperation.execute_ability_attack(
            state, attacker_id, sid, dmg, dmg, pierce, hits, damage_profile="Flame", is_melee=False)
        splash.append({"target": sid, "attack": satk})
    tp = state.get_entity(target_id)
    tpc = tp.get_component(PositionComponent) if tp is not None else None
    ttile = state.board.id_at(tpc.col, tpc.row) if tpc is not None else None
    ignited = []
    if ttile is not None:
        for ntile in state.board.neighbours(ttile):
            if state.rng.next_bool(fire_of_absolution_ignite_chance()):
                if AddEffectOperation.execute(state, source=attacker_id, target=ntile,
                                              effect_type=FIRE_TILE, name="Fire") is not None:
                    ignited.append(ntile)
    if not splash and not ignited:
        return []
    return [{"passive": "FireOfAbsolution", "by": attacker_id, "on": target_id,
             "splash": splash, "ignited_tiles": ignited}]


def _pick_target_with_splash(state, caster_id):
    """Cible ENNEMIE dont le SELECTEUR DE SPLASH natif rend >=1 unite (splash non vide = chemin exerce)."""
    cteam = _team(state, caster_id)
    sel = _splash_selector()
    for tid in state.entities:
        if _team(state, tid) == cteam or not _alive(state, tid):
            continue
        ents = entities_from_state(state, caster_id, tid)
        if any(u.get("id") is not None for u in sel.evaluate(ents)):
            return tid
    return None


def test_fire_of_absolution_migration_matches_imperative(live_session, rpc, build_runner):
    """Le nouveau `_fire_of_absolution_after_attack` (arbre DSL `fire_of_absolution_tree`) reproduit l'ANCIEN
    corps hybride imperatif BIT-EXACT : meme set + per-coup de splash, memes tuiles ignitees, sous le MEME
    `state.rng` seede, sur DEUX etats INDEPENDANTS issus de la MEME capture LIVE."""
    rid = build_runner("777", extra=BUILD)["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    # native_sym = adjacence unite-unite CORRECTE (mirror natif). Les DEUX faces (arbre + ref) PARTAGENT ce
    # board -> la branche ignite (board.neighbours) est identique quel que soit le mode (replay-diff board-agnostique).
    board = Board(bg["tiles"], adjacency="native_sym")

    st0 = load_state(dv, ob, snap, board=board)
    if st0.effects is None:
        pytest.skip("EffectsState non charge (combatSnapshot absent) -> gate FireOfAbsolution KO")
    caster_id = next((eid for eid in st0.entities
                      if _visual(st0, eid) == CASTER_VIS and _alive(st0, eid)
                      and st0.get_entity(eid).get_component(StatsComponent) is not None), None)
    if caster_id is None:
        pytest.skip("caster adeptRetributor (StatsComponent) introuvable offline")
    target_id = _pick_target_with_splash(st0, caster_id)
    if target_id is None:
        pytest.skip("aucune cible ennemie avec occupant adjacent (splash FireOfAbsolution non exercable)")

    # DEUX etats INDEPENDANTS depuis la MEME capture, MEME board, seedes IDENTIQUEMENT -> arbre vs ref.
    st_new = load_state(dv, ob, snap, board=board); st_new.rng = _seed_rng(s0)
    st_ref = load_state(dv, ob, snap, board=board); st_ref.rng = _seed_rng(s0)

    res_new = _fire_of_absolution_after_attack(st_new, caster_id, target_id, ranged=True)   # arbre DSL migre
    res_ref = _fire_of_absolution_imperative_ref(st_ref, caster_id, target_id, ranged=True)  # ancien imperatif

    new_splash, ref_splash = _splash_map(res_new), _splash_map(res_ref)
    new_ign, ref_ign = _ignited(res_new), _ignited(res_ref)

    print(f"\n[FIREOFABS migration] caster={caster_id} target={target_id}")
    print(f"[FIREOFABS migration] splash new={ {k: new_splash[k] for k in sorted(new_splash)} } "
          f"ref={ {k: ref_splash[k] for k in sorted(ref_splash)} }")
    print(f"[FIREOFABS migration] ignited new={sorted(new_ign)} ref={sorted(ref_ign)}")

    # 0) le passif a REELLEMENT fire (splash non vide) -> arbre exerce
    assert ref_splash, "splash FireOfAbsolution vide cote reference -> chemin non exerce (setup)"
    # 1) MEME set + per-coup de splash (feuille AttackWithAbilityDamage multi == boucle execute_ability_attack)
    assert new_splash == ref_splash, f"splash arbre {new_splash} != imperatif {ref_splash}"
    # 2) MEMES tuiles ignitees (Foreach(AdjacentTiles, Maybe(30, SetOnFire)) == boucle ignite next_bool)
    assert new_ign == ref_ign, f"ignited arbre {sorted(new_ign)} != imperatif {sorted(ref_ign)}"
