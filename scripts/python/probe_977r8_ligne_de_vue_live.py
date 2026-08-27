r"""#977-r8 -- CONFRONTATION LIVE : le domaine `tile_aim` du port contre le NATIF.

QUESTION. #977-r7 a cable la ZONE de `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` ;
#977-r8 y ajoute le `RemoveAll(b__1)` de LIGNE DE VUE. Ce probe demande au NATIF, sans capteur
neuf, quelles tuiles il juge ciblables -- et compare aux DEUX regimes du port (AVANT le cablage,
APRES).

L'ORACLE est le RPC `abilityTargets` : c'est
`IdunBattle.Core.Services.BattleQuery$$GetAllValidTargetsFromAllPossibleMovementTiles` /
`AttackQuery$$GetValidTargets`, donc la cascade de ciblage NATIVE, `GetPossibleTargetsForOptions`
compris. Aucune invocation ecrivante, aucune reinjection.

PORTEUR : `darkaAzrael` (lineup, DANS le pool) porte `1092 DarkTalonStrike` -- routee `tile_aim`,
`reach = 2`, AUCUN des deux bits `AllowObscuredTargetBy*` et PAS de `TargetMatchesDynamicRule`.
C'est donc l'ability ou la ligne de vue est le SEUL filtre que cette tranche ajoute : tout ecart
mesure lui est imputable, sans etage tiers a demeler.

CE QUE LE PROBE REND, ET CE QU'IL NE PEUT PAS RENDRE
-----------------------------------------------------
Il rend trois ensembles de tuiles -- `natif`, `port_apres`, `port_avant` -- et leurs differences.
Le verdict qu'il cherche est : `port_apres` PLUS PROCHE de `natif` que `port_avant`, et jamais
plus loin. Sur un board SANS relief entre le caster et sa couronne, les trois coincident : c'est
un accord en regime DEGENERE, qui ne prouve RIEN -- le probe le DIT (`REGIME DEGENERE`) au lieu
de le rendre en vert, et invite a changer de board.

⚠ **L'ORACLE N'EST PAS LE MEME ARTEFACT QUE LA ZONE, ET LA MESURE LE MONTRE.** Run du 2026-08-18,
runner 73, board `MC1_67`, seed 777, Azrael pose en (2,4) et `orksNob` en (3,4) :

    natif = 1 tuile -- **(3,4)**, c'est-a-dire EXACTEMENT la tuile occupee par l'ennemi
    port APRES = 17   port AVANT = 18

`abilityTargets` rend la LEGALITE du cast (`AttackQuery$$GetValidTargets`, qui applique EN PLUS
la cascade `GetInvalidTargetReason` per-ability), pas l'ensemble que `GetPossibleTargetsForOptions`
ENUMERE. Ce que la confrontation etablit donc, et c'est ce qui importe pour une correction
permissive -> moins-permissive :

  * `natif \ APRES` = **VIDE** -- le cablage n'introduit AUCUN faux negatif : il ne retire rien de
    ce que le natif garde ;
  * `AVANT \ APRES` = **{(2,2)}** -- il retire une tuile que le natif ne garde pas non plus, donc
    l'ecart symetrique DECROIT (17 -> 16).

Ce qu'elle N'ETABLIT PAS : que le port ait atteint la zone native. Les 16 tuiles restantes ne
relevent NI de `b__1` (porte, et ce board n'a aucun mur -- le volet elevation n'en retire qu'une)
NI de `b__2` (`1092` ne porte pas `TargetMatchesDynamicRule` : mesure). Elles relevent d'un etage
TIERS, la cascade de validite de cible. Residu `#977-r11`.

`--board` est OBLIGATOIRE a l'appelant. Le probe ne monte pas de runner lui-meme : il s'attache a
un `--state-file` deja construit, pour que le choix de board et de placement reste explicite.

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

import engine.ai.state_bridge as SB                                          # noqa: E402
from engine.services import targeting_query as TQ                            # noqa: E402
from rl_collect_batch import _rpc                                            # noqa: E402

DARK_TALON_STRIKE = 1092


def _r(sid, method, body, timeout=90):
    res = _rpc(sid, method, [body], timeout=timeout)
    return res.get("result") if isinstance(res, dict) and "result" in res else res


def _porteur(state, visual_id="darkaAzrael"):
    from engine.runner.components import UnitComponent                       # noqa: PLC0415
    for eid, e in state.entities.items():
        u = e.get_component(UnitComponent)
        if u is not None and u.alive and (u.visual_id or "") == visual_id:
            return eid
    return None


def _session_id(sf: dict):
    s = sf.get("session")
    return s.get("id") if isinstance(s, dict) else s


def _tuiles_natives(sid, rid, uid, ability_id, champ="targets") -> set:
    at = _r(sid, "abilityTargets",
            {"runnerId": rid, "unitId": uid, "abilityType": ability_id}) or {}
    for u in (at.get("units") or []):
        if u.get("unitId") != uid:
            continue
        for a in (u.get("abilities") or []):
            return {(t["tile"]["col"], t["tile"]["row"])
                    for t in (a.get(champ) or [])
                    if t.get("kind") == "tile" and t.get("tile")}
    return set()


def _tuiles_port(state, uid, ability_id, champ="targets") -> set:
    rep = SB.ability_targets_offline(state, uid, ability_id) or {}
    for u in (rep.get("units") or []):
        for a in (u.get("abilities") or []):
            return {(t["tile"]["col"], t["tile"]["row"])
                    for t in (a.get(champ) or [])
                    if t.get("kind") == "tile" and t.get("tile")}
    return set()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state-file", required=True,
                    help="ABSOLU, deja construit par `rl_duel build --board <id>`")
    ap.add_argument("--unit", type=int, default=None, help="uid du porteur (defaut : auto)")
    ap.add_argument("--ability", type=int, default=DARK_TALON_STRIKE)
    ap.add_argument("--champ", choices=("targets", "fromHere"), default="fromHere",
                    help="`fromHere` = depuis la position COURANTE, le seul regime ou le port et "
                         "le natif partagent le meme ensemble de tuiles-caster")
    args = ap.parse_args(argv)

    sf = json.loads(Path(args.state_file).read_text(encoding="utf-8"))
    sid, rid = _session_id(sf), sf.get("runnerId")
    print("session=%s runner=%s ability=%s champ=%s" % (sid, rid, args.ability, args.champ))

    from engine.entities.pathfinding.board import Board                      # noqa: PLC0415
    from engine.runner.snapshot import load_state                            # noqa: PLC0415

    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        print("NON MESURE : `boardGraph` indisponible -- pas un zero.")
        return 99
    tuiles_bg = bg["tiles"]
    murs = sum(1 for t in tuiles_bg if t.get("isWall"))
    elevs = sorted({int(t.get("elevation") or 0) for t in tuiles_bg})
    print("board : %d tuiles, %d mur(s), elevations %s" % (len(tuiles_bg), murs, elevs))
    state = load_state(dv, ob, snap, board=Board(tuiles_bg, adjacency="native_sym"))
    uid = args.unit if args.unit is not None else _porteur(state)
    if uid is None:
        print("NON MESURE : aucun `darkaAzrael` vivant dans l'etat charge.")
        return 99
    print("porteur uid=%s" % uid)

    natif = _tuiles_natives(sid, rid, uid, args.ability, args.champ)
    apres = _tuiles_port(state, uid, args.ability, args.champ)

    # REGIME D'AVANT, rejoue TEL QUEL : le meme corps, sans le `RemoveAll(b__1)`.
    vrai = TQ.target_is_obscured
    try:
        TQ.target_is_obscured = lambda *a, **k: False        # noqa: E731
        avant = _tuiles_port(state, uid, args.ability, args.champ)
    finally:
        TQ.target_is_obscured = vrai

    print("\n  natif      : %3d tuiles" % len(natif))
    print("  port APRES : %3d tuiles" % len(apres))
    print("  port AVANT : %3d tuiles" % len(avant))
    print("  AVANT \\ APRES (ce que le cablage RETIRE) : %s" % sorted(avant - apres))
    print("  natif \\ APRES (le port en manque)        : %s" % sorted(natif - apres))
    print("  APRES \\ natif (le port en a en trop)     : %s" % sorted(apres - natif))
    print("  natif \\ AVANT                            : %s" % sorted(natif - avant))
    print("  AVANT \\ natif (le SUR-ENSEMBLE d'avant)  : %s" % sorted(avant - natif))

    if avant == apres:
        print("\n  REGIME DEGENERE : le cablage ne retire RIEN sur ce board -- les deux regimes du "
              "port coincident, donc l'accord (ou le desaccord) avec le natif ne dit rien de "
              "CETTE tranche. Changer de board (relief entre le caster et sa couronne) ou "
              "DEPLACER le caster (`--place`).")
        return 99

    ecart_apres = len(apres ^ natif)
    ecart_avant = len(avant ^ natif)
    print("\n  ecart symetrique au natif : AVANT=%d  APRES=%d" % (ecart_avant, ecart_apres))
    if ecart_apres < ecart_avant:
        print("  VERDICT : le cablage RAPPROCHE le port du natif (%d -> %d)."
              % (ecart_avant, ecart_apres))
        return 0
    if ecart_apres == ecart_avant:
        print("  VERDICT : ecart INCHANGE -- le cablage retire des tuiles, mais pas celles que le "
              "natif retire. A demeler avant de conclure.")
        return 1
    print("  ROUGE : le cablage ELOIGNE le port du natif (%d -> %d)." % (ecart_avant, ecart_apres))
    return 1


if __name__ == "__main__":
    sys.exit(main())
