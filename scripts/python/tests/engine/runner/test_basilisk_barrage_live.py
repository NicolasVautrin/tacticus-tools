"""BasiliskBarrage (1026, `astraOrdnance` « Thaddeus Noble ») FACE COMBAT (execute) confronte LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.BasiliskBarrageAbility$$ExecuteBehaviour` (DECOMPILE) :
    total      = Direct(GetNumberConstant(0x1f) = nrOfProjectiles)
    guaranteed = Min( Max(0, StatAmount(Caster@0x160, 0xc = TurnsStarted) - 1), total )
    miss       = Max( 0, total - GetNumberConstant(0x38 = nrOfProjectiles_2) - guaranteed )
    maybe      = Max( 0, total - (guaranteed + miss) )
    sel = Cache(PickRandomly(TilesAtDistance(Target,2),                     miss,       1, 0x7fffffff))
        + Cache(PickRandomly(TargetTiles@0x190 + TilesAtDistance(Target,1), maybe,      1, 0x7fffffff))
        + Cache(PickRandomly(TargetTiles@0x190,                             guaranteed, 1, 0x7fffffff))
    Execute( AtomicGroup(0x54, AttackWithAbilityDamage(Caster@0x160, sel, MinMaxDamage,
                                                       GetDamageProfile(0)=Blast,
                                                       GetNumberConstant(0x2f)=nrOfHits)) )

AVANT ce port, 1026 etait absente du registre de combat -> `ported:False` = **0 degat, aucune erreur**
(divergence d'etat SILENCIEUSE). Ce fichier est le GARDE de non-regression de ce trou.

Ce que ces tests PROUVENT (montage `ring_scenario`, cf. `_ringed_cast.py`) :
  (1) LOI DES OBUS : `nrOfProjectiles` obus au total ; `miss` tombent a distance EXACTEMENT 2 de la
      tuile ciblee, les autres sur {tuile ciblee} u anneau 1 ; le tirage est AVEC REMISE
      (`allowRepeat=1`) donc deux obus PEUVENT tomber sur la meme tuile -> une unite peut encaisser
      2x `nrOfHits` coups. Chaque unite touchee encaisse un MULTIPLE de `nrOfHits`.
  (2) `guaranteed` CROIT AVEC LES ROUNDS TERMINES (`TurnsStarted(caster) - 1`) : au 1er tour du caster
      aucun obus n'est garanti sur la tuile ciblee, apres N rounds N le sont (i2 : « For each round
      that has ended, 1 more of the shells hits the target hex »).
  (3) FIDELITE DU DEGAT : per-coup offline == per-coup live coup par coup (meme MT seede) -- ce qui
      valide d'un bloc le TIRAGE des tuiles (pools + ordre cube natif + remise), l'ordre d'attaque
      (id de tuile ASC), la famille d'operation (ABILITY : 1 tirage/coup, aucun crit) et les
      bornes/profil/percage. Les tuiles VIDES touchees sont confrontees aussi
      (`Damage_Empty_Target_Tile_Id` live vs `AttackEmptyTile` porte).

Le caster n'est JAMAIS deplace : son masque de ciblage porte `CasterHasNotMoved` (lu au ctor), donc
un caster ayant bouge verrait son cast REFUSE -- par le natif comme par le port.
Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

import gameconfig as GC
import hexgeo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _ringed_cast import cast_and_confront, counts, ring_scenario   # noqa: E402

ORD = "astraOrdnance"                                   # id 1026 BasiliskBarrage
ALLY = "astraCreed"
ENEMIES = "necroOverlord,necroWarden,necroDestroyer,necroSpyder"
BUILD = ["--p-units", f"{ORD},{ALLY}", "--a-units", ENEMIES,
         "--hp-target", "120000", "--hp-player", "120000", "--no-ai"]
ABILITY = 1026


def _consts():
    c = (GC.ability("BasiliskBarrage") or {}).get("constants") or {}
    return (int(c.get("nrOfProjectiles") or 0), int(c.get("nrOfProjectiles_2") or 0),
            int(c.get("nrOfHits") or 0))


def _off_seq(diag):
    out = []
    for s in (diag.get("attacks") or []):
        out += [(s["target"], a) for a in ((s.get("attack") or {}).get("per_hit") or [])]
    return out


def _setup(rpc, rid, rounds: int):
    sc = ring_scenario(rpc, rid, ORD, ALLY, rounds=rounds, place_caster_adjacent=False)
    if sc.get("reason"):
        pytest.skip(sc["reason"])
    return sc


def _assert_shell_law(sc, diag, live, empty, expect_guaranteed):
    """Loi des obus (comptes + zones) sur le rendu PORTE, confronte au live."""
    total, second, hits = _consts()
    shells = diag.get("shells") or {}
    tiles = list(diag.get("tiles") or [])
    board, tp, ttile = sc["board"], sc["tpos"], sc["ttile"]
    assert shells.get("total") == total, f"total obus {shells} != nrOfProjectiles {total}"
    assert shells.get("guaranteed") == expect_guaranteed, (
        f"guaranteed {shells.get('guaranteed')} != rounds termines {expect_guaranteed}")
    assert shells["guaranteed"] + shells["maybe"] + shells["miss"] == total, f"tranches {shells}"
    assert shells["miss"] == max(0, total - second - shells["guaranteed"]), f"miss {shells}"
    assert len(tiles) == total, f"{len(tiles)} tuiles d'impact != {total} obus ({tiles})"
    n_miss = sum(1 for t in tiles if hexgeo.distance(tp, board.coord(t)) == 2)
    n_near = sum(1 for t in tiles if hexgeo.distance(tp, board.coord(t)) <= 1)
    assert n_miss == shells["miss"], f"{n_miss} obus a distance 2 != miss {shells['miss']} ({tiles})"
    assert n_near == shells["guaranteed"] + shells["maybe"], (
        f"{n_near} obus a distance <=1 != guaranteed+maybe ({tiles})")
    assert tiles.count(ttile) >= shells["guaranteed"], (
        f"seulement {tiles.count(ttile)} obus sur la tuile ciblee, {shells['guaranteed']} garantis")
    # chaque unite touchee prend un MULTIPLE de nrOfHits (1 obus = nrOfHits coups)
    for uid, n in counts(live).items():
        assert n % hits == 0, f"u{uid}: {n} coups live n'est pas un multiple de nrOfHits {hits}"
    # les tuiles VIDES touchees == celles du port (multi-ensemble)
    assert sorted(empty) == sorted(diag.get("empty") or []), (
        f"tuiles vides live {sorted(empty)} != port {sorted(diag.get('empty') or [])}")
    # total obus live (unites + vides) == nrOfProjectiles
    assert sum(counts(live).values()) // hits + len(empty) == total, (
        f"obus live {counts(live)} + vides {empty} != {total}")


def test_basilisk_barrage_first_turn_live(live_session, rpc, build_runner):
    """1er tour du caster (`TurnsStarted=1`) : AUCUN obus garanti -> `nrOfProjectiles_2` sur
    {cible} u anneau 1 et le reste a distance EXACTEMENT 2 ; per-coup offline == live."""
    total, second, hits = _consts()
    assert total > 0 and hits > 0, "constantes nrOfProjectiles/nrOfHits absentes du gameconfig 1026"
    rid = build_runner("777", extra=BUILD)["rid"]
    sc = _setup(rpc, rid, rounds=0)
    live, empty, off, diag = cast_and_confront(rpc, rid, sc, ABILITY, _off_seq)
    if diag.get("cast_ko"):
        pytest.skip(f"cast KO: {diag['cast_ko']}")
    assert diag.get("ported"), f"ability {ABILITY} non routee par le wiring ability-exec: {diag}"
    print(f"\n[BASILISK t1] cible={sc['target']} shells={diag.get('shells')} "
          f"tiles={diag.get('tiles')}")
    print(f"[BASILISK t1] live={counts(live)} off={counts(off)} vides live={empty}")
    _assert_shell_law(sc, diag, live, empty, expect_guaranteed=0)
    assert (diag.get("shells") or {}).get("maybe") == second, (
        f"maybe {diag.get('shells')} != nrOfProjectiles_2 {second} au 1er tour")
    assert counts(off) == counts(live), f"coups OFFLINE {counts(off)} != LIVE {counts(live)}"
    assert off == live, f"per-coup OFFLINE != LIVE\noff ={off}\nlive={live}"
    print("[BASILISK t1] OK : loi des obus + per-coup bit-exact")


def test_basilisk_barrage_guaranteed_grows_live(live_session, rpc, build_runner):
    """Apres 2 rounds termines : 2 obus GARANTIS sur la tuile ciblee (i2 « 1 more per round that has
    ended ») -> l'occupant encaisse au moins 2x nrOfHits coups ; per-coup offline == live."""
    _total, _second, hits = _consts()
    rid = build_runner("31337", extra=BUILD)["rid"]
    sc = _setup(rpc, rid, rounds=2)
    live, empty, off, diag = cast_and_confront(rpc, rid, sc, ABILITY, _off_seq)
    if diag.get("cast_ko"):
        pytest.skip(f"cast KO: {diag['cast_ko']}")
    assert diag.get("ported"), f"ability {ABILITY} non routee par le wiring ability-exec: {diag}"
    print(f"\n[BASILISK t3] cible={sc['target']} shells={diag.get('shells')} "
          f"tiles={diag.get('tiles')}")
    print(f"[BASILISK t3] live={counts(live)} off={counts(off)} vides live={empty}")
    _assert_shell_law(sc, diag, live, empty, expect_guaranteed=2)
    # la CIBLE occupe la tuile garantie -> au moins guaranteed x nrOfHits coups
    assert counts(live).get(sc["target"], 0) >= 2 * hits, (
        f"cible u{sc['target']}: {counts(live).get(sc['target'], 0)} coups live < 2 obus garantis "
        f"x nrOfHits {hits}")
    assert counts(off) == counts(live), f"coups OFFLINE {counts(off)} != LIVE {counts(live)}"
    assert off == live, f"per-coup OFFLINE != LIVE\noff ={off}\nlive={live}"
    print("[BASILISK t3] OK : guaranteed=2 + per-coup bit-exact")
