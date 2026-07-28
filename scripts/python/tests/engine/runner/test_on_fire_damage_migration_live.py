"""#149 slice-15 : OnFireDamage (pose du FEU on-hit, `Damage.Loki`) MIGRATION vers l'arbre DSL
`on_fire_damage_tree()` (mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour`, RE decompile).

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
from engine.runner.operations.triggers.dispatch import damage_dealt_triggers
from engine.runner.operations.triggers.loki import FIRE_TILE
from engine.entities.damage_trait import DamageTrait
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine/runner -> import du helper sibling

from _on_hit_tile_effect_replay import replay_on_hit_tile_effect   # noqa: E402

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
    """Copie de l'ANCIEN corps imperatif : gate profil OnFire + PositionComponent -> board.id_at ->
    AddEffectOperation. ORACLE du replay-diff (ne passe NI par l'arbre NI par le bus).

    `source=tile_id` : la surcharge `AddEffect` a 5 arguments passe un selecteur SOURCE **NUL**, et
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` retombe alors sur la CIBLE -- ground
    truth live du JUMEAU (meme surcharge, memes arguments) : `FleshMetalGuns_TileEffectAbility` pose
    DespoiledGround avec `source` = l'id de la TUILE (#85). L'oracle portait encore le caster."""
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
    eff = AddEffectOperation.execute(state, source=tile_id, target=tile_id,
                                     effect_type=FIRE_TILE, name="Fire")
    if eff is None:
        return []
    return [{"tile_effect": "Fire", "placed_on_tile": tile_id, "by": attacker_id,
             "on": target_id, "placement": "OnFireDamage"}]


def _on_fire_via_bus(state, attacker_id, target_id, profile):
    """Emet le vecteur `On(DamageDealt = 0x10)` -- le SEUL chemin du canal `OnFireDamageAbility` depuis
    le de-fork (registre `GLOBAL_TRIGGERS`). Filtre sur `placement` pour isoler CE consommateur des
    deux autres auditeurs du meme vecteur (`FleshmetalGuns`, `OnToxicDamageAbility`)."""
    out = damage_dealt_triggers(state, attacker_id, target_id, profile=profile, is_first_hit=True)
    return [r for r in (out or []) if r.get("placement") == "OnFireDamage"]


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
    st0 = load_state(dv, ob, snap, board=board)
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

    st_new = load_state(dv, ob, snap, board=board)
    st_ref = load_state(dv, ob, snap, board=board)

    res_new = _on_fire_via_bus(st_new, attacker_id, target_id, PROFILE)              # bus On(0x10)
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
    # 3) SOURCE de l'effet = la TUILE, pas le caster. La surcharge `AddEffect` a 5 arguments passe un
    #    selecteur SOURCE NUL et `AddEffectBehaviour$$Execute` retombe sur la CIBLE ; ground truth live
    #    du JUMEAU DespoiledGround (#85 : `source` = l'id de tuile, jamais celui de Volk). Le port
    #    passait le caster -- residu ferme, cette garde l'empeche de revenir.
    for t in new_tiles:
        srcs = {e.source for e in st_new.effects.active_effects(t) if e.effect_type == fire}
        assert srcs == {t}, (
            f"source de l'effet Fire {srcs} != la TUILE {t} : la surcharge `AddEffect` a 5 args passe "
            f"un selecteur SOURCE NUL, donc `AddEffectBehaviour$$Execute` retombe sur la CIBLE "
            f"(attacker={attacker_id})")


# --------------------------------------------------------- GENERALISATION : les COUPS BONUS (#179)

BONUS_CARRIER = "blackObliterator"      # « Volk » — HERO, present dans `rl_duel build --list-pool`
BONUS_ESCORT = "adeptHospitaller"
BONUS_FOES = "necroWarden,necroWarden"


def test_on_fire_from_bonus_hit_group_agrees_with_live(live_session, rpc, build_runner):
    """ELARGISSEMENT mesure du DE-FORK : les GROUPES DE COUPS BONUS (#179) emettent eux aussi le
    vecteur `On(0x10)`, avec LEUR profil -- ce que l'appel imperatif ne pouvait pas faire.

    Avant le de-fork, le canal `OnFireDamageAbility` etait appele UNE fois par attaque avec le SEUL
    profil de l'arme primaire. Depuis, il est consommateur du bus, emis par `_apply_damage_pipeline`
    a CHAQUE groupe de degat resolu -- y compris les sous-operations de coups additionnels
    (`operations/additional_hits.py`, mirror `IdunBattle.Operations.
    ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`). C'est la place NATIVE : chaque coup
    passe par `IdunBattle.Operations.ApplyDamageOperation$$Execute`, qui emet `On(0x10)` avec le profil
    DE CE COUP.

    PORTEUR CHOISI, et c'est le seul point qui rend le test discriminant : `blackObliterator` (« Volk »)
    n'a AUCUNE arme au profil `OnFire` (`Power` 4 coups, `HeavyRound` 6 coups r3) -- mais son passif
    `FleshmetalGuns` fait tourner un cycle d'effets d'arme dont `FleshmetalGunsRuinousSalvo` (0x4bc)
    accorde **+2 coups de profil `Flame`** (le seul profil portant `OnFire`). Une attaque de Volk pendant
    ce round-la est donc le regime EXACT ou l'ancien port ne pouvait pas poser de feu et ou le nouveau
    le peut. Si l'elargissement etait FAUX, on verrait offline une tuile en feu que le live n'a pas.

    Le test n'impose PAS d'atteindre le round RuinousSalvo (la rotation est pilotee par
    `UnitTurnsStarted mod 3`, cf. `loki/fleshmetal_guns.py`) : il confronte TOUTES les attaques et exige
    l'accord bit-a-bit du verdict de feu ET des PV. Un desaccord dans un sens comme dans l'autre est un
    echec -- c'est ce qui fait de ce test une garde de l'elargissement, pas une simple repetition."""
    conf, _rid = replay_on_hit_tile_effect(
        rpc, build_runner, carrier_vis=BONUS_CARRIER, effect_type=FIRE_TILE,
        p_units=f"{BONUS_CARRIER},{BONUS_ESCORT}", a_units=BONUS_FOES,
        stop_on_placement=False, max_attacks=9)
    real = [c for c in conf if not c.get("noop")]
    print(f"\n[ONFIRE bonus-hits] confrontations={len(real)} "
          f"(noop ignores={len(conf) - len(real)}) poses live={sum(1 for c in real if c['live_effect'])}")
    for c in real:
        print(f"[ONFIRE bonus-hits] profile={c['profile']} hits={c['hits']} hp live={c['live_hp']} "
              f"off={c['off_hp']} fire live={c['live_effect']} off={c['off_effect']} "
              f"tile={c['tile']} mt_same={c['mt_same']}")
    assert real, (f"aucune attaque de {BONUS_CARRIER} confrontee au live -- l'elargissement du de-fork "
                  f"aux groupes de coups bonus n'a rien valide")
    # CE QUE CE TEST GARDE : le VERDICT DE FEU, seul observable du canal `On(0x10)` sur ce porteur.
    for c in real:
        assert c["off_effect"] == c["live_effect"], (
            f"feu sur la tuile {c['tile']} : offline={c['off_effect']} live={c['live_effect']} -- le "
            f"vecteur `On(0x10)` emis par les groupes de coups BONUS pose (ou ne pose pas) du feu la ou "
            f"le natif fait l'inverse. C'est l'elargissement du de-fork qui est en cause, pas le canal "
            f"lui-meme (l'attaque primaire de {BONUS_CARRIER} n'a aucun profil OnFire)")
    # LES PV, DESORMAIS GARDES -- mais SEULEMENT quand `mt_same` (case-o10 SS 6, RESOLU).
    # L'ecart historique (live 2668 / offline 1440 des la 1re attaque) N'ETAIT PAS un ecart du modele
    # de degat : `drive_to_firing_position` DEPLACE Volk avant de tirer, et `load_state` ne
    # reconstruisait pas `UnitFlag.Moved` -> le gate no-move de
    # `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` ne mordait
    # jamais et l'offline accordait un +25% ranged que le natif refuse (l'offline rendait EXACTEMENT
    # la meme valeur qu'immobile -- signature d'un gate aveugle). Ferme par
    # `snapshot._load_unit_flags` (seed depuis `combatSnapshot.units[].unitFlags`).
    #
    # POURQUOI GATER SUR `mt_same` PLUTOT QU'ASSERTER TOUT : `mt_same` signifie que l'offline a
    # consomme EXACTEMENT les memes tirages que le live, donc que la SEQUENCE DE COUPS concorde ; les
    # PV doivent alors concorder aussi, et c'est precisement le regime ou l'ecart de magnitude vivait.
    # Les confrontations `mt_same=False` relevent d'un AUTRE residu, de CARDINALITE (le groupe
    # FleshmetalGuns/LetTheGalaxyBurn manque parfois offline : live 9 coups / offline 8 ou 6) --
    # documente a part, et qu'on ne veut pas importer ici.
    for c in real:
        if not c["mt_same"]:
            continue
        assert c["off_hp"] == c["live_hp"], (
            f"PV cible offline={c['off_hp']} live={c['live_hp']} alors que le flux MT est IDENTIQUE "
            f"(memes tirages, meme sequence de coups) : la magnitude par coup diverge. Suspect n1 = "
            f"un gate d'etat de l'ATTAQUANT non reconstruit par `load_state` (c'est `UnitFlag.Moved` "
            f"qui a produit ce symptome, cf. case-o10 SS 6)")
    diverging = [c for c in real if c["off_hp"] != c["live_hp"]]
    if diverging:
        print(f"[ONFIRE bonus-hits] RESIDU DE CARDINALITE (mt_same=False, hors perimetre) : "
              f"{len(diverging)}/{len(real)} attaques aux PV divergents "
              f"{[(c['live_hp'], c['off_hp']) for c in diverging]}")
