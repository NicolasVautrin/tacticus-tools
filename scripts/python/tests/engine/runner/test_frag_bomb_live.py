"""FragBomb (1017, `astraBullgryn` « Kut Skoden ») FACE COMBAT (execute) confronte LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$ExecuteBehaviour` (DECOMPILE) :
    splash = AdjacentUnits(Target@0x178, 0, 3) - Caster@0x160     # = Units(AdjacentTiles(t)) - t - caster
    main   = AttackDamage(Caster@0x160, ActiveTarget@0x180, MinMaxDamage, GetDamageProfile(0)=Blast,
                          Get(GetNumberConstant(0x2f) = nrOfHits))
    splashA= idem avec Get(GetNumberConstant(0x32) = nrOfHits_2)
    ExecuteAtomic( SortedAttackSeries(Caster@0x160, Units(Target@0x178,1,1), main, splash, splashA), .., 0x43 )

AVANT ce port, 1017 etait absente du registre de combat -> `ported:False` = **0 degat, aucune erreur**
(divergence d'etat SILENCIEUSE). Ce fichier est le GARDE de non-regression de ce trou.

Ce que ces tests PROUVENT (montage `ring_scenario`, cf. `_ringed_cast.py` : les DEUX camps sont drives
-- `applyAction` ignore propriete et portee -- pour poser une geometrie exacte) :
  (1) GEOMETRIE `crowded` : la cible encaisse `nrOfHits` coups ; CHAQUE unite adjacente a la tuile
      ciblee en encaisse `nrOfHits_2` -- **y compris un ALLIE du caster** (friendly-fire, i2 « ALL
      units adjacent to the target hex, except Kut Skoden himself ») -- et le CASTER n'encaisse RIEN.
  (2) GEOMETRIE `alone` : cible isolee -> AUCUN volet splash, seulement `nrOfHits` sur la cible
      (prouve que le splash n'est pas un forfait).
  (3) ORDRE : `SortedAttackSeries` n'a AUCUN `OrderBy` -- il itere le selecteur. L'ordre porte doit
      donc etre `cible` puis le voisinage NATIF de la tuile ciblee (`Board.neighbours_native`).
  (4) FIDELITE DU DEGAT : per-coup offline == per-coup live, coup par coup (meme MT seede) -- ce qui
      valide d'un bloc bornes/profil/percage ET l'ordre (qui fixe la sequence de tirages).

RESIDU CONNU, HORS PORT (R32 de `port-residuals-inventory.md`, mesure par
`probe_avalanche_charge_gate.py`) : si le caster A BOUGE pendant le tour du cast (CHARGE), le natif
ajoute `AvalancheOfMuscle_ExtraDamage` (effet 1025 du passif du porteur, gate `IsCharging`) =
+`extraDmg[niveau passif] x multiplicateur` FLAT par coup sur les ennemis ADJACENTS au caster. Ce gate
n'est PAS porte et se reproduit A L'IDENTIQUE sur l'ATTAQUE NORMALE du meme porteur (donc PAS un
defaut de ce port). `ring_scenario(rounds=1)` cast depuis un tour ou le caster n'a pas bouge.

Lit l'etat LIVE, aucune tuile/RVA hardcodee, seed = simple generateur. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

import gameconfig as GC

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _ringed_cast import cast_and_confront, counts, ring_scenario   # noqa: E402

BULL = "astraBullgryn"                                  # id 1017 FragBomb
ALLY = "astraCreed"                                     # allie -> confronte le FRIENDLY-FIRE
ENEMIES = "necroOverlord,necroWarden,necroDestroyer,necroSpyder"
BUILD = ["--p-units", f"{BULL},{ALLY}", "--a-units", ENEMIES,
         "--hp-target", "120000", "--hp-player", "120000", "--no-ai"]
ABILITY = 1017


def _consts():
    c = (GC.ability("FragBomb") or {}).get("constants") or {}
    return int(c.get("nrOfHits") or 0), int(c.get("nrOfHits_2") or 0)


def _off_seq(diag):
    """per-coup du diagnostic moteur, dans l'ordre d'execution de l'arbre."""
    out = [(diag.get("target"), a)
           for a in ((diag.get("main_attack") or {}).get("per_hit") or [])]
    for s in (diag.get("splash") or []):
        out += [(s["target"], a) for a in ((s.get("attack") or {}).get("per_hit") or [])]
    return out


def _setup(rpc, rid, isolate: bool):
    sc = ring_scenario(rpc, rid, BULL, ALLY, rounds=1, place_caster_adjacent=True,
                       isolate_target=isolate)
    if sc.get("reason"):
        pytest.skip(sc["reason"])
    return sc


def test_frag_bomb_crowded_live(live_session, rpc, build_runner):
    """Cible ENTOUREE : nrOfHits sur la cible, nrOfHits_2 sur CHAQUE adjacent (allie compris), 0 sur
    le caster ; ordre = voisinage natif ; per-coup offline == live."""
    h1, h2 = _consts()
    assert h1 > 0 and h2 > 0, "constantes nrOfHits/nrOfHits_2 absentes du gameconfig 1017"
    rid = build_runner("777", extra=BUILD)["rid"]
    sc = _setup(rpc, rid, isolate=False)
    if len(sc["ring_units"]) < 2:
        pytest.skip(f"splash attendu trop petit: {sc['ring_units']}")
    if sc["ally"] not in sc["ring_units"]:
        pytest.skip("l'allie n'est pas adjacent a la cible (friendly-fire non exerce)")
    live, _empty, off, diag = cast_and_confront(rpc, rid, sc, ABILITY, _off_seq)
    if diag.get("cast_ko"):
        pytest.skip(f"cast KO: {diag['cast_ko']}")
    assert diag.get("ported"), f"ability {ABILITY} non routee par le wiring ability-exec: {diag}"
    lc, oc = counts(live), counts(off)
    print(f"\n[FRAGBOMB crowded] cible={sc['target']} splash attendu={sc['ring_units']} "
          f"ordre={diag.get('order')}")
    print(f"[FRAGBOMB crowded] live={lc} off={oc}")

    # (1) COUPS : cible = nrOfHits ; chaque splash = nrOfHits_2 ; caster = RIEN
    assert lc.get(sc["target"]) == h1, f"cible: LIVE {lc.get(sc['target'])} coups != nrOfHits {h1}"
    for uid in sc["ring_units"]:
        assert lc.get(uid) == h2, f"splash u{uid}: LIVE {lc.get(uid)} coups != nrOfHits_2 {h2}"
    assert sc["me"] not in lc, f"le CASTER a encaisse du splash live: {lc}"
    assert set(lc) == {sc["target"], *sc["ring_units"]}, (
        f"ensemble touche live {set(lc)} != cible+adjacents "
        f"{set([sc['target'], *sc['ring_units']])}")
    # FRIENDLY-FIRE : l'allie du caster est bien dans le splash
    assert lc.get(sc["ally"]) == h2, (
        f"friendly-fire: l'allie u{sc['ally']} n'a pas pris {h2} coups: {lc}")
    # (2) le PORT rend exactement les memes coups
    assert oc == lc, f"coups OFFLINE {oc} != LIVE {lc}"
    # (3) ORDRE natif : cible d'abord, puis le voisinage NATIF (aucun OrderBy dans SortedAttackSeries)
    assert diag.get("order") == [sc["target"], *sc["ring_units"]], (
        f"ordre porte {diag.get('order')} != cible + voisinage natif "
        f"{[sc['target'], *sc['ring_units']]}")
    # (4) DEGAT bit-exact, coup par coup
    assert off == live, f"per-coup OFFLINE != LIVE\noff ={off}\nlive={live}"
    print("[FRAGBOMB crowded] OK : coups+friendly-fire+ordre+per-coup bit-exact")


def test_frag_bomb_alone_live(live_session, rpc, build_runner):
    """Cible ISOLEE : AUCUN splash, seulement nrOfHits sur la cible ; per-coup offline == live."""
    h1, _h2 = _consts()
    rid = build_runner("31337", extra=BUILD)["rid"]
    sc = _setup(rpc, rid, isolate=True)
    if sc["ring_units"]:
        pytest.skip(f"geometrie isolee non atteinte (splash={sc['ring_units']})")
    live, _empty, off, diag = cast_and_confront(rpc, rid, sc, ABILITY, _off_seq)
    if diag.get("cast_ko"):
        pytest.skip(f"cast KO: {diag['cast_ko']}")
    assert diag.get("ported"), f"ability {ABILITY} non routee par le wiring ability-exec: {diag}"
    lc = counts(live)
    print(f"\n[FRAGBOMB alone] cible={sc['target']} live={lc} ordre={diag.get('order')}")
    assert lc == {sc["target"]: h1}, f"cible isolee : LIVE {lc} != {{cible: {h1}}}"
    assert not diag.get("splash"), (
        f"le port a produit un splash sur une cible isolee: {diag.get('splash')}")
    assert off == live, f"per-coup OFFLINE != LIVE\noff ={off}\nlive={live}"
    print("[FRAGBOMB alone] OK : splash vide + per-coup bit-exact")
