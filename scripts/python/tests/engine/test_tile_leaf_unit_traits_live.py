"""#175 -- GARDE : le `ctx` des feuilles Tile(7) porte `unit_traits`, et le gate de trait MORD.

Defaut corrige : `tile_leaf_ctx` (`engine/utilities/tile.py`) n'emettait PAS la cle `unit_traits`,
lue 12 fois dans le meme module par 7 feuilles. `_has` etant strict (cle absente -> False), les 7
gates rendaient 0.0 EN SILENCE -- degradation PERMISSIVE : ni erreur, ni test rouge.

Ces gardes se confrontent au LIVE (aucune valeur de tuile en dur) et couvrent DEUX etages, dans
l'ordre de la doctrine « decomposer par etage » :

  etage 1 -- le CTX : la cle arrive-t-elle jusqu'a `BaseUtility.evaluate(self, tile, meta, ctx, wt)`,
             sur les DEUX chemins natifs qui emettent la meme `ComposedUtility` Tile(7) (sweep MOVE
             via `MovementActionGenerator` et terme Tile(7) de l'ATTAQUE via
             `engine.playbook.base.tile_utility`) ? Et son CONTENU est-il celui que le natif
             interrogerait (`IdunBattle.Entities.UnitExtensions$$HasTrait`) -- pseudo-trait de
             grande-alliance COMPRIS, alors qu'il est absent de tout kit gameconfig ?

  etage 2 -- l'EFFET : sur une tuile qui porte REELLEMENT l'effet `DespoiledGround` (EffectType
             `0x5c4` = 1476, pose par le NATIF), la feuille `DespoiledGroundUtility` rend-elle
             `ChaosAffectedUnit` (-5) pour un porteur Chaos et `ImperialAndXenosAffectedUnit` (-25)
             pour un Imperial, et 0 sur une tuile temoin ? Les deux poids sont LUS de la BC, jamais
             ecrits en dur.

Montage : fixture nommee et reutilisable `tests/engine/_tile_leaf_montage.py`.
ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

import gameconfig as GC
from engine.ai import context as _ai_ctx
from engine.entities.traits.unit_trait import UnitTrait, grand_alliance_trait_name
from engine.utilities.tile import TILE_LEAF_IDS, TILE_LEAVES, tile_leaf_ctx

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from _tile_leaf_montage import build_despoiled_montage  # noqa: E402


@pytest.fixture(scope="module")
def despoiled(rpc, build_runner):
    """Bataille ou le NATIF a pose `DespoiledGround` sur une tuile (cf. `_tile_leaf_montage`)."""
    return build_despoiled_montage(rpc, build_runner)


# ------------------------------------------------------------------ etage 1 : le ctx


class _Spy:
    """Capture les cles du `ctx` qui atteint REELLEMENT chaque feuille, sans changer la valeur."""

    def __init__(self):
        self._saved = []
        self.keys: set = set()
        self.calls = 0

    def __enter__(self):
        for i in TILE_LEAF_IDS:
            _n, leaf = TILE_LEAVES.get(i, (None, None))
            if leaf is None:
                continue
            orig = leaf.evaluate
            spy = self

            def ev(tile, meta, ctx, wt, _orig=orig):
                spy.keys.update((ctx or {}).keys())
                spy.calls += 1
                return _orig(tile, meta, ctx, wt)

            self._saved.append((leaf, orig))
            leaf.evaluate = ev
        return self

    def __exit__(self, *exc):
        for leaf, orig in self._saved:
            leaf.evaluate = orig
        self._saved = []
        return False


def test_unit_traits_reaches_the_leaves_on_both_native_paths(rpc, despoiled):
    """La cle `unit_traits` atteint `BaseUtility.evaluate` sur le sweep MOVE **et** sur le terme
    Tile(7) de l'ATTAQUE. Sans elle, 7 feuilles rendent 0.0 en silence."""
    from engine.ai.action_generators import MovementActionGenerator
    from engine.playbook.base import tile_utility

    ctx = despoiled.ctx_carrier
    seen = {}
    for label, run in (("MOVE", lambda: MovementActionGenerator().generate(ctx)),
                       ("ATTACK", lambda: tile_utility(ctx, ctx.origin))):
        with _Spy() as spy:
            run()
        seen[label] = (spy.calls, sorted(spy.keys))
        print("[#175 %s] appels=%d cles=%s" % (label, spy.calls, sorted(spy.keys)))

    for label, (calls, keys) in seen.items():
        assert calls > 0, ("chemin %s : AUCUNE feuille Tile(7) evaluee -- la garde ne prouve rien"
                           % label)
        assert "unit_traits" in keys, (
            "chemin %s : le ctx qui atteint BaseUtility.evaluate N'A PAS `unit_traits` -> les 7 "
            "feuilles a gate de trait (CapturePoint 24, PowerUp 26, DespoiledGround 28, "
            "SummonDislikeDoorOpening 29, HeroLikeDoorOpening 30, AttractMechanicals 57, "
            "MasterOfTheTutelaries 62) rendent 0.0 EN SILENCE. cles vues : %s" % (label, keys))


def test_unit_traits_mirrors_hastrait_including_grand_alliance(rpc, despoiled):
    """Le CONTENU de `unit_traits` = ce que `UnitExtensions$$HasTrait` interrogerait : les traits
    du kit gameconfig **plus** le pseudo-trait de GRANDE-ALLIANCE (`GrandAlliance$$GetTrait` :
    Imperial=26, Xenos=1006, Chaos=2026), lequel n'est dans AUCUN kit -- c'est precisement le piege
    qu'un port naif rate."""
    dv = rpc("decisionView", {"runnerId": despoiled.rid, "allAbilities": True}, 150)
    mov = rpc("aiMovableTiles", {"runnerId": despoiled.rid}, 150)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    rpc_l = lambda m, b, t: rpc(m, b, t)                                   # noqa: E731

    checked = 0
    for u in (dv.get("units") or []):
        if not u.get("alive"):
            continue
        vis = u.get("visualId")
        ctx = _ai_ctx.build(rpc_l, despoiled.rid, dv, mov_by_unit, u["id"],
                            despoiled.wt, despoiled.ctx_carrier.predictor)
        leaf = tile_leaf_ctx(ctx)
        assert "unit_traits" in leaf, (
            "`tile_leaf_ctx` n'emet PAS la cle `unit_traits` -> `_has` (strict) rend False pour "
            "TOUT trait et les 7 gates rendent 0.0 en silence. cles emises : %s"
            % sorted(leaf.keys()))
        got = set(leaf["unit_traits"])
        kit = set((GC.unit(vis) or {}).get("traits") or ())
        want = {int(UnitTrait[n]) for n in kit}
        ga = grand_alliance_trait_name(vis)
        assert ga is not None, "unite %s sans GrandAllianceId -- montage inattendu" % vis
        want.add(int(UnitTrait[ga]))
        print("[#175 traits] u%s %-20s kit=%s alliance=%s -> ids=%s"
              % (u["id"], vis, sorted(kit), ga, sorted(got)))
        assert got == want, ("unite %s : unit_traits=%s attendu %s (kit gameconfig + trait "
                             "d'alliance derive)" % (vis, sorted(got), sorted(want)))
        # l'id d'alliance N'EST PAS dans le kit : sans la derivation, DespoiledGround serait muet
        assert int(UnitTrait[ga]) not in {int(UnitTrait[n]) for n in kit}, (
            "le trait d'alliance %s est present dans le kit gameconfig de %s -- la premisse du "
            "port (derivation depuis GrandAllianceId) serait fausse" % (ga, vis))
        checked += 1
    assert checked >= 2, "moins de 2 unites confrontees (%d)" % checked


# ------------------------------------------------------------------ etage 2 : l'effet


def test_despoiled_ground_gate_bites_per_grand_alliance(despoiled):
    """Sur la tuile que le NATIF a despoilee, la feuille `DespoiledGroundUtility` rend le poids BC
    de la grande-alliance de l'unite qui evalue -- et 0 sur la tuile temoin. Les deux branches
    (`ChaosAffectedUnit` / `ImperialAndXenosAffectedUnit`) sont confrontees dans la MEME mesure."""
    leaf = TILE_LEAVES[28][1]
    wt = despoiled.wt
    w_chaos = wt.sub("DespoiledGround", "ChaosAffectedUnit")
    w_imp = wt.sub("DespoiledGround", "ImperialAndXenosAffectedUnit")
    assert w_chaos < 0 and w_imp < 0, "poids BC DespoiledGround inattendus (%s / %s)" % (w_chaos,
                                                                                        w_imp)

    ids = despoiled.tile_effect_types.get(despoiled.pos_despoiled) or []
    assert 1476 in ids, ("la tuile %s ne porte pas l'EffectType 1476 (%s) -- montage casse"
                         % (despoiled.pos_despoiled, ids))

    meta_d = {"tile_effect_type_ids": ids}
    meta_c = {"tile_effect_type_ids": despoiled.tile_effect_types.get(despoiled.pos_clean) or []}
    ctx_c = tile_leaf_ctx(despoiled.ctx_carrier)      # Chaos
    ctx_t = tile_leaf_ctx(despoiled.ctx_target)       # Imperial
    assert int(UnitTrait.Chaos) in (ctx_c.get("unit_traits") or ()), (
        "le ctx du porteur ne porte pas le trait Chaos (2026) : unit_traits=%s -> la branche "
        "ChaosAffectedUnit de DespoiledGround est INATTEIGNABLE"
        % (ctx_c.get("unit_traits"),))
    assert int(UnitTrait.Imperial) in (ctx_t.get("unit_traits") or ()), (
        "le ctx de la cible ne porte pas le trait Imperial (26) : unit_traits=%s -> la branche "
        "ImperialAndXenosAffectedUnit de DespoiledGround est INATTEIGNABLE"
        % (ctx_t.get("unit_traits"),))

    v_chaos = leaf.evaluate(despoiled.pos_despoiled, meta_d, ctx_c, wt)
    v_imp = leaf.evaluate(despoiled.pos_despoiled, meta_d, ctx_t, wt)
    v_clean_c = leaf.evaluate(despoiled.pos_clean, meta_c, ctx_c, wt)
    v_clean_i = leaf.evaluate(despoiled.pos_clean, meta_c, ctx_t, wt)
    print("[#175 despoil] tuile=%s ids=%s | Chaos=%s (BC %s) Imperial=%s (BC %s) "
          "| temoin=%s Chaos=%s Imperial=%s"
          % (despoiled.pos_despoiled, ids, v_chaos, w_chaos, v_imp, w_imp,
             despoiled.pos_clean, v_clean_c, v_clean_i))

    assert v_chaos == w_chaos, "branche Chaos: %s attendu %s" % (v_chaos, w_chaos)
    assert v_imp == w_imp, "branche Imperial/Xenos: %s attendu %s" % (v_imp, w_imp)
    assert v_clean_c == 0 and v_clean_i == 0, (
        "tuile temoin non nulle (%s / %s) -- le gate ne serait pas conditionnel"
        % (v_clean_c, v_clean_i))
    assert v_chaos != v_imp, ("les deux branches rendent la meme valeur -> le gate de trait ne "
                              "discrimine pas la grande-alliance")


def test_tile_meta_carries_effect_type_ids_end_to_end(despoiled):
    """Le CO-GATE metadata arrive jusqu'a la feuille par le chemin REEL (`tile_utility`), pas
    seulement dans un `meta` fabrique par le test : le composite Tile(7) evalue sur la tuile
    despoilee doit differer de sa valeur « gate neutralise » d'exactement le poids BC."""
    from engine.playbook.base import tile_utility

    ctx = despoiled.ctx_target                  # Imperial -> branche a -25 (la plus lourde)
    w_imp = despoiled.wt.sub("DespoiledGround", "ImperialAndXenosAffectedUnit")
    total = tile_utility(ctx, despoiled.pos_despoiled)

    leaf = TILE_LEAVES[28][1]
    saved = leaf.evaluate
    try:                                        # meme appel, feuille DespoiledGround neutralisee
        leaf.evaluate = lambda *a, **k: 0.0
        total_off = tile_utility(ctx, despoiled.pos_despoiled)
    finally:
        leaf.evaluate = saved
    print("[#175 e2e] Tile(7)@%s avec=%s sans=%s delta=%s (BC %s)"
          % (despoiled.pos_despoiled, total, total_off, total - total_off, w_imp))
    assert total - total_off == w_imp, (
        "le co-gate `meta.tile_effect_type_ids` n'atteint PAS la feuille par le chemin reel : "
        "delta %s attendu %s" % (total - total_off, w_imp))
