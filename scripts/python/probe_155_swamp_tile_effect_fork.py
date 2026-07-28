"""PROBE case-155 -- le `-25 Swamp` a UN SEUL foyer, et il ne double JAMAIS.

RESIDU NOMME de #146 : le savoir « terrain STATIQUE -> noms sommes par la feuille TileEffects(9) »
vivait dans DEUX tables offline -- `utilities/tile.py::TERRAIN_TILE_EFFECTS` (DryBush -> LightCover)
et `runner/operations/spawn.py::_PLACEMENT_TERRAIN_EFFECTS` (Swamp -> Thorns_DefenseReduction), cette
derniere lue par UN SEUL call-site. Fork de port : 1 concept natif, 2 implementations qui derivent.

CE QUE DIT LE DECOMPILE (`IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`) :
deux boucles, deux SOURCES, deux espaces de NOMS.
  Loop1 : `GetComponent<EffectsOwnedComponent>(mainTile)` -> par effet possede,
          `name = ((EffectType)EffectComponent+0x58).ToString()`, poids `Default.TileEffects.<EffectType>`,
          multiplie par `IdunBattle.AI.Utilities.TileEffectsUtility$$GetStatusEffectMultiplier` SEULEMENT si
          `StaticBattleRules.Effect$$IsTileStatusEffect`.
  Loop2 : collection d'abilities HEBERGEES -> `Unit.get_Id` -> `ActiveAbilityType.ToString()`,
          poids `Default.TileEffects.<AbilityName>`, SANS multiplicateur.

Et `IdunBattleLogic.Entities.Abilities.Tiles.ThornsBlockMovementAbility$$CreateBehaviour` (l'ability
hebergee par Swamp) = `AddBlockEnteringUnitsEffect(0) & AddStaticStatModifierEffectToOwner(0xb, 3,
Direct(const 0x14))` : le -25 est un effet POSE SUR LA TUILE, donc **Loop1**, pas Loop2 (aucune cle BC
`SwampBlockMovement`/`ThornsBlockMovement` n'existe dans `Default.TileEffects` -> `HasUtilityValue`
est FAUX pour Loop2 sur une Swamp). Le canal juste est donc le canal DYNAMIQUE
(`state.effects.by_unit[tileId]`, seede par `load_state(tiles=tileMeta)`, case-102) ; la table statique
n'est qu'un REPLI pour les etats non hydrates (`tiles=` est opt-in).

CE QUE CE PROBE MESURE (3 volets, live) :
  A. la geometrie qui a IMPOSE le -25 (case-130 SS5, caster force sur t15 de MC1_67) rend toujours
     `t24 Swamp u=25` et le port place ou le live place ;
  B. REGIME HYDRATE vs NON HYDRATE : le meme replay avec `load_state(tiles=tileMeta)` rend les MEMES
     tuiles -- c'est LA garantie anti-fork (les deux canaux convergent au lieu de s'additionner) ;
  C. TEMOIN : repli neutralise (`TERRAIN_TILE_OWNED_EFFECTS` vide) sur un etat NON hydrate -> le port
     place sur la Swamp, DIFFERENT du live. Sans ce volet, A ne prouverait pas que le -25 DECIDE.

Usage :  python probe_155_swamp_tile_effect_fork.py [--seed 777] [--board MC1_67] [--caster-tile 15]
Depuis scripts/python. ASCII only. Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import probe_130_placement_sort_rng as P  # noqa: E402  (harnais live REUTILISE, pas duplique)


def _replay(reg, tiles=None, owned_effects=None):
    """Rejoue le cast par le PORT REEL et rend les tuiles de spawn.

    `tiles` : payload `tileMeta` -> etat HYDRATE (le canal dynamique porte les effets de tuile).
    `owned_effects` : substitution de `utilities/tile.py::TERRAIN_TILE_OWNED_EFFECTS` (volet TEMOIN).
    """
    from engine.runner.snapshot import load_state
    from engine.runner.components import PositionComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.utilities import tile as T

    st = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"], tiles=tiles)
    st.rng = P.CountingRng(reg["rng_before"]["mt"], reg["rng_before"]["mti"])
    before_ids = set(st.entities.keys())
    saved = T.TERRAIN_TILE_OWNED_EFFECTS
    if owned_effects is not None:
        T.TERRAIN_TILE_OWNED_EFFECTS = owned_effects
    try:
        Runner(st).install_default_handlers(20).apply(
            AttackUnitMessage(reg["cid"], reg["target"]))
    finally:
        T.TERRAIN_TILE_OWNED_EFFECTS = saved
    out = []
    for eid in st.entities:
        if eid in before_ids:
            continue
        pc = st.get_entity(eid).get_component(PositionComponent)
        if pc is not None:
            t = reg["board"].id_at(pc.col, pc.row)
            if t is not None:
                out.append(t)
    return st.rng.n, sorted(out)


def _pool_utilities(reg, tiles=None, owned_effects=None):
    """(pool ordre natif, {tuile: utilite Tile(7)}) tels que `_sort_tiles_by_utility_for_summon` les voit."""
    from engine.runner.snapshot import load_state
    from engine.runner.operations import spawn as SP
    from engine.utilities import tile as T

    st = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"], tiles=tiles)
    pool = SP._free_tiles_adjacent(st, reg["cid"], set(), native_order=True)
    saved = T.TERRAIN_TILE_OWNED_EFFECTS
    if owned_effects is not None:
        T.TERRAIN_TILE_OWNED_EFFECTS = owned_effects
    try:
        order = SP._sort_tiles_by_utility_for_summon(st, pool, reg["cid"])
    finally:
        T.TERRAIN_TILE_OWNED_EFFECTS = saved
    return pool, order, st


def _tile_effect_names(st, tile_id):
    if st.effects is None:
        return []
    return sorted(e.name for e in st.effects.by_unit.get(int(tile_id), []) if not e.consumed and e.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=P.BOARD)
    ap.add_argument("--caster-tile", type=int, default=15)
    args = ap.parse_args()
    P.BOARD = args.board
    rpc = P.Rpc()
    print("session=%s seed=%s board=%s caster_tile=%s"
          % (rpc.sid, args.seed, P.BOARD, args.caster_tile))

    reg = P.run_case(rpc, args.seed, "controledict", discriminate=True,
                     force_caster_tile=args.caster_tile)
    if reg is None or "rng_after" not in reg:
        print("SCENARIO INDISPONIBLE (setup a re-crafter, pas un verdict)")
        return 2
    try:
        tm = rpc("tileMeta", {"runnerId": reg["rid"]}, 60)
        live = reg["live_spawn_tiles"]
        board = reg["board"]

        # ---- volet A : regime NON hydrate (celui de la garde #130)
        pool, order_dry, st_dry = _pool_utilities(reg)
        n_dry, tiles_dry = _replay(reg)
        swamps = [t for t in pool if board.tile_def_id(t) == "Swamp"]
        print("\n[A] regime NON hydrate (load_state sans tiles=)")
        print("  pool ordre natif      : %s" % pool)
        print("  terrains              : %s" % [(t, board.tile_def_id(t)) for t in pool])
        print("  tri par utilite       : %s" % order_dry)
        print("  effets de tuile lus   : %s" % {t: _tile_effect_names(st_dry, t) for t in pool})
        print("  LIVE tiles=%s | PORT tiles=%s genrand=%s  %s"
              % (live, tiles_dry, n_dry, "OK" if tiles_dry == live else "MISMATCH"))

        # ---- volet B : regime HYDRATE (tiles=tileMeta) -- doit CONVERGER, pas s'ajouter
        pool_h, order_h, st_h = _pool_utilities(reg, tiles=tm)
        n_h, tiles_h = _replay(reg, tiles=tm)
        print("\n[B] regime HYDRATE (load_state tiles=tileMeta) -- anti-double-comptage")
        print("  effets de tuile lus   : %s" % {t: _tile_effect_names(st_h, t) for t in pool_h})
        print("  tri par utilite       : %s" % order_h)
        print("  LIVE tiles=%s | PORT tiles=%s genrand=%s  %s"
              % (live, tiles_h, n_h, "OK" if tiles_h == live else "MISMATCH"))
        print("  convergence des deux regimes : %s"
              % ("OK (meme ordre, meme tuile)" if (order_h == order_dry and tiles_h == tiles_dry)
                 else "DIVERGENT -- le repli s'ADDITIONNE au canal dynamique (fork rouvert)"))

        # ---- volet C : TEMOIN -- repli neutralise sur etat NON hydrate
        _, order_no, _ = _pool_utilities(reg, owned_effects={})
        n_no, tiles_no = _replay(reg, owned_effects={})
        print("\n[C] TEMOIN : repli Loop1 neutralise, etat NON hydrate")
        print("  tri par utilite       : %s" % order_no)
        print("  PORT tiles=%s (live %s)  %s"
              % (tiles_no, live,
                 "DIFFERENT du live -> le -25 DECIDE" if tiles_no != live
                 else "IDENTIQUE au live -> scenario NON discriminant (re-crafter)"))

        ok = (tiles_dry == live and tiles_h == live and order_h == order_dry
              and tiles_no != live and bool(swamps))
        print("\n=== VERDICT === %s" % ("OK" if ok else "KO"))
        print("  swamps dans le pool : %s" % swamps)
        return 0 if ok else 1
    finally:
        try:
            rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
        except Exception:
            pass
        try:
            reg["state_file"].unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
