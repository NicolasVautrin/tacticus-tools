"""#149 slice-15 : OnFireDamage (pose du FEU on-hit, `Damage.Loki`) MIGRATION vers l'arbre DSL
`on_fire_damage_tree()` (mirror 1:1 de `OnFireDamageAbility.CreateBehaviour @1811c3a60`, RE decompile).

Arbre natif (noeud DSL UNIQUE) :
    AddEffect( 5 (FireEffect), source = AbilityStateReference, target = Tiles(target@0x178) )
= pose l'effet FEU DE TUILE sur la MainTile OCCUPEE de la cible quand un coup d'arme au profil `OnFire`
(gameconfig `damage_profile[...]['Traits']`) touche. La feuille `AddEffect` (GENERALISEE tile-domain :
`Tiles(Target())` rend la position de la cible -> `_add_effect_target_id` la convertit en id de tuile)
route vers `AddEffectOperation.execute(target=tile_id, FIRE_TILE, "Fire")` = MEME Operation/args que
l'ancien imperatif. On confronte le NOUVEAU `_on_fire_damage_ability` (qui DELEGUE a l'arbre) a une COPIE
de reference de l'ANCIEN corps imperatif (PositionComponent -> board.id_at -> AddEffectOperation).
REPLAY-DIFF sur DEUX etats INDEPENDANTS issus de la MEME capture LIVE -> MEME tuile ignitee + effet FEU
REELLEMENT present sur la meme tuile = BIT-EXACT (RNG-free : AddEffect inconditionnel).

Cible = 1re unite ENNEMIE avec une position sur le board. Profil = "Flame" (skip si son gameconfig ne
porte pas le trait OnFire, i.e. gate `DamageProfileHasTrait(OnFire)` non exercable). Lit l'etat LIVE.
ASCII-only. NON committe (tests confront live, hors depot)."""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.components import OwnerComponent, UnitComponent, PositionComponent, StatsComponent
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.operations.triggers import _on_fire_damage_ability
from engine.runner.operations.triggers.loki import FIRE_TILE
from engine.entities.damage_trait import DamageTrait
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board

PROFILE = "Flame"                      # profil OnFire de l'attaque (skip si le trait manque)
BUILD = ["--roster", "1", "--p-units", "adeptRetributor",
         "--a-units", "necroWarden,necroDestroyer,necroSpyder,necroOverlord"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _team(state, eid):
    e = state.get_entity(eid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _alive(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.alive if uc is not None else True


def _has_pos(state, eid):
    e = state.get_entity(eid)
    return e is not None and e.get_component(PositionComponent) is not None


def _on_fire_damage_imperative_ref(state, attacker_id, target_id, profile):
    """Copie VERBATIM de l'ANCIEN corps de `_on_fire_damage_ability` (AVANT slice-15) : gate profil OnFire
    + PositionComponent -> board.id_at -> AddEffectOperation. ORACLE du replay-diff (ne passe PAS par l'arbre)."""
    if not profile or state.effects is None or getattr(state, "board", None) is None:
        return []
    import gameconfig as GC
    traits = (GC.damage_profile(profile) or {}).get("Traits") or []
    if DamageTrait.OnFire.name not in traits:
        return []
    te = state.get_entity(target_id)
    pc = te.get_component(PositionComponent) if te is not None else None
    if pc is None:
        return []
    tile_id = state.board.id_at(pc.col, pc.row)          # Tiles(cible@0x178) = tuile occupee courante
    if tile_id is None:
        return []
    eff = AddEffectOperation.execute(state, source=attacker_id, target=tile_id,
                                     effect_type=FIRE_TILE, name="Fire")
    if eff is None:
        return []
    return [{"tile_effect": "Fire", "placed_on_tile": tile_id, "by": attacker_id,
             "on": target_id, "placement": "OnFireDamage"}]


def _placed_tiles(res):
    return sorted(p.get("placed_on_tile") for p in (res or []) if p.get("placed_on_tile") is not None)


def test_on_fire_damage_migration_matches_imperative(live_session, rpc, build_runner):
    """Le nouveau `_on_fire_damage_ability` (arbre DSL `on_fire_damage_tree`) reproduit l'ANCIEN corps
    imperatif BIT-EXACT : MEME tuile ignitee + effet FEU present sur la meme tuile, sur DEUX etats
    INDEPENDANTS issus de la MEME capture LIVE (RNG-free)."""
    rid = build_runner("777", extra=BUILD)["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")

    # gate DamageProfileHasTrait(OnFire) : le profil "Flame" doit porter le trait OnFire pour exercer le chemin.
    import gameconfig as GC
    traits = (GC.damage_profile(PROFILE) or {}).get("Traits") or []
    if DamageTrait.OnFire.name not in traits:
        pytest.skip(f"profil {PROFILE} sans trait OnFire -> chemin OnFireDamage non exercable")

    board = Board(bg["tiles"], adjacency="native_sym")
    st0 = load_state(dv, ob, snap); st0.board = board
    if st0.effects is None:
        pytest.skip("EffectsState non charge (combatSnapshot absent) -> AddEffect KO")

    # attaquant = 1re unite JOUEUR (source de l'effet, identite indifferente pour OnFireDamage) ;
    # cible = 1re unite ENNEMIE VIVANTE avec position (Tiles(target) exige une MainTile).
    attacker_id = next((eid for eid in st0.entities
                        if _alive(st0, eid) and st0.get_entity(eid).get_component(StatsComponent) is not None
                        and _team(st0, eid) is not None), None)
    if attacker_id is None:
        pytest.skip("aucun attaquant (StatsComponent) offline")
    ateam = _team(st0, attacker_id)
    target_id = next((eid for eid in st0.entities
                      if _team(st0, eid) not in (None, ateam) and _alive(st0, eid) and _has_pos(st0, eid)), None)
    if target_id is None:
        pytest.skip("aucune cible ennemie avec position (Tiles(target) non exercable)")

    st_new = load_state(dv, ob, snap); st_new.board = board
    st_ref = load_state(dv, ob, snap); st_ref.board = board

    res_new = _on_fire_damage_ability(st_new, attacker_id, target_id, PROFILE)       # arbre DSL migre
    res_ref = _on_fire_damage_imperative_ref(st_ref, attacker_id, target_id, PROFILE)  # ancien imperatif

    new_tiles, ref_tiles = _placed_tiles(res_new), _placed_tiles(res_ref)
    print(f"\n[ONFIREDMG migration] attacker={attacker_id} target={target_id} profile={PROFILE}")
    print(f"[ONFIREDMG migration] placed new={new_tiles} ref={ref_tiles}")

    fire = int(EffectType.Fire)
    # 0) le chemin a REELLEMENT pose du feu cote reference (tuile propre au depart) -> arbre exerce
    assert ref_tiles, "aucune tuile ignitee cote reference -> chemin non exerce (setup)"
    # 1) MEME tuile ignitee (Tiles(Target()) tile-domain == PositionComponent -> board.id_at)
    assert new_tiles == ref_tiles, f"tuile arbre {new_tiles} != imperatif {ref_tiles}"
    # 2) effet FEU REELLEMENT present sur la meme tuile dans les DEUX etats (mutation identique)
    for t in new_tiles:
        assert st_new.effects.has_effect(t, effect_type=fire), f"arbre: pas d'effet Fire sur tuile {t}"
        assert st_ref.effects.has_effect(t, effect_type=fire), f"ref: pas d'effet Fire sur tuile {t}"
