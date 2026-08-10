"""`#589-r1-r1-r2-r1-r4` -- CONFRONTATION du capteur `adjacentTilesNative`.

## Le critere binaire, enonce AVANT la mesure

`case-589-r1-r1-r2-r1` sec.6 a mesure, sur `C3_14`, porteur en `(5,4)` et compagnon en `(5,3)` :
l'arete est ABSENTE de `boardGraph.neighbours` ET de `connectivity`, dans les deux sens, et
pourtant le natif COMPTE le compagnon (l'effet s'active et retranche `495 x 1`). La fiche en
concluait que `AdjacentTilesSelector` et `BattleQuery$$IterateAdjacentTiles` << ne lisent pas le
meme substrat >> -- conclusion REFUTEE par la chaine d'appel relue (cf. `rpc-adjacency.ts` : le
selecteur passe par le slot 80 d'`IBattleQuery`, qui EST `IterateAdjacentTiles`).

Reste donc UNE question, et une seule :

    `adjacentTilesNative` sur l'origine `(5,4)`, regime `selector` (les arguments EXACTS
    d'`AdjacentTilesSelector$$Select`), rend-il `(5,3)` ?

  * OUI  -> la capture `boardGraph` est INCOMPLETE. `diag.unmappedNeighbours` (ici) et
            `boardGraph.diag.adjUnmapped` disent de combien ; le correctif est dans le remapping.
  * NON  -> le natif ne compte pas ce voisin PAR CE CHEMIN, et c'est la mesure de la fiche
            (qui infere << le natif compte >> depuis l'ACTIVITE de l'effet) qu'il faut reprendre.

Un capteur qui ne repond pas n'est PAS un verdict : `diag.calls == 0` ou un `error` par origine
fait sortir en rc 2 (MONTAGE), jamais en rc 0/1.

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


class MontageError(RuntimeError):
    """On REFUSE de rendre un verdict plutot que d'en fabriquer un depuis un capteur muet."""


def _build(state_file: str, seed: str, board: str, roster: int) -> int:
    # `--roster` : `C3_14` n'a que 4 spawns par camp -- le defaut de 5 fait REFUSER le build
    # (`4 spawns joueur < 5 units`). Le montage ne lit que des TUILES, donc le roster n'a
    # aucun role au-dela d'exister.
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
            "--roster", str(roster), "--state-file", state_file, "--no-ai"]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        raise MontageError("rl_duel build a echoue (rc=%d) : %s"
                           % (p.returncode, (p.stderr or p.stdout or "")[-900:]))
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def _fmt(tiles) -> str:
    return ", ".join("(%s,%s)%s" % (t.get("col"), t.get("row"),
                                    "" if t.get("projected") else "*NONPROJETE")
                     for t in tiles)


def montage_geo(a) -> int:
    """MODE `--montage-geo` : la MEME mesure, mais DANS le montage `--geo-only` du probe amulette.

    C'est le seul regime ou la contradiction se lit : le bras `geo-only` place le porteur en `(5,4)`
    et un compagnon en `(5,3)`, arete ABSENTE du substrat stocke, et le natif ACTIVE quand meme
    l'effet. Interroger `adjacentTilesNative` sur une bataille VIDE ne peut pas trancher pourquoi :
    il faut le demander sur l'ENTITE du porteur, pendant que le compagnon est pose.

    `entityIds` est ce que la sec.8.2 de la case-doc prescrit et que le mode tuile ne fait pas :
    `BattleQuery.<IterateAdjacentTiles>d__95$$MoveNext` resout son `from` par
    `EntityExtensions$$IterateTiles`, donc c'est la forme EXACTE que prend l'appel quand le DSL
    passe `Owner` -- ce que fait `AdjacentFriends(Owner@DSLSelectors+0x30, 1, 3)`.
    """
    import argparse as _ap
    import rl_collect_batch as R
    import probe_589r1r1r2r1_amulet_crit_reduction_live as AM
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    from engine.runner import snapshot as SNAP

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        r = R._rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    SNAP.bind_live_rpc(rpc)
    ns = _ap.Namespace(seed=a.seed, board=a.board, crit_damage=2000,
                       trait="Decoy", geo_only=True, verbose=True)
    rid, sf = AM.build(ns, "r4geo", a.level)
    if rid is None:
        raise MontageError("le build du montage geo a echoue (voir la ligne `build KO` ci-dessus)")
    print("runner %s | montage GEO du probe amulette (board %s, niveau %d)"
          % (rid, a.board, a.level))
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 120)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = AM.stage(h, 1, verbose=True, geo_only=True)
        if rec is None:
            print("")
            print("=== le montage GEO a REFUSE : %s" % why)
            print("Le bras `_stage_geo` refuse notamment quand le natif n'active PAS l'effet.")
            print("Dans ce cas la mesure de `case-589` sec.6 ne se reproduit pas -- ce qui est")
            print("DEJA un resultat, coherent avec le mode tuile.")
            return 1
        carrier_id = rec["target"]
        geo = rec.get("geo")
        dv = h.dview()
        cu = next((u for u in (dv.get("units") or []) if u.get("id") == carrier_id), None)
        cpos = (cu or {}).get("pos") or {}
        comp = next((u for u in (dv.get("units") or [])
                     if ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row")) == geo),
                    None)
        print("")
        print("=== le montage, tel qu'il est REELLEMENT pose ===")
        print("  porteur   u%s pos=(%s,%s) feet=%r"
              % (carrier_id, cpos.get("col"), cpos.get("row"), (cu or {}).get("feet")))
        print("  compagnon u%s pos=%s feet=%r"
              % ((comp or {}).get("id"), geo, (comp or {}).get("feet")))
        print("  effet actif cote NATIF = %s" % rec.get("actif_natif"))

        print("")
        print("=== la MESURE : `adjacentTilesNative` sur l'ENTITE du porteur ===")
        ids = [carrier_id] + ([comp["id"]] if comp else [])
        res = rpc("adjacentTilesNative", {"runnerId": rid, "entityIds": ids}, 120)
        if not res.get("ok"):
            raise MontageError("adjacentTilesNative rend ok=false : %s" % res.get("error"))
        print("  diag = %s" % json.dumps(res.get("diag") or {}, sort_keys=True))
        contient = None
        for r in (res.get("origins") or []):
            print("  origine id=%s kind=%s originTiles=%s"
                  % (r.get("originId"), r.get("kind"), r.get("originTiles")))
            for rn, rv in (r.get("byRegime") or {}).items():
                if "error" in rv:
                    raise MontageError("regime %s en erreur : %s" % (rn, rv["error"]))
                print("     %-8s count=%d : %s"
                      % (rn, rv.get("count", 0), _fmt(rv.get("tiles") or [])))
                if r.get("originId") == carrier_id and rn == "selector":
                    contient = any((int(t.get("col")), int(t.get("row"))) == tuple(geo)
                                   for t in (rv.get("tiles") or []))

        print("")
        print("=== VERDICT BINAIRE (montage GEO) ===")
        print("  le natif ACTIVE l'effet          : %s" % rec.get("actif_natif"))
        print("  `AdjacentTiles(Owner)` porte %s : %s" % (geo, contient))
        if rec.get("actif_natif") and contient is False:
            print("VERDICT : les DEUX sont vrais et ils sont INCOMPATIBLES par le chemin suppose.")
            print("  `AdjacentFriends(Owner,1,3)` = `Friends(unit, Units(AdjacentTiles(unit),..) -")
            print("  unit, ..)` ne peut pas rendre un compagnon dont la tuile n'est PAS dans")
            print("  `AdjacentTiles(Owner)`. L'activation vient donc d'AILLEURS que de ce compagnon,")
            print("  ou d'un autre chemin -- c'est la mesure de `case-589` sec.6 qui doit etre reprise,")
            print("  et non le capteur : il repond, et il repond NON.")
            return 1
        if rec.get("actif_natif") and contient:
            print("VERDICT : l'entite REND l'arete que la TUILE ne rend pas -- l'ecart est dans")
            print("  la resolution du `from` (`EntityExtensions$$IterateTiles`), pas dans le ring-1.")
            return 0
        print("VERDICT : regime non discriminant (effet inactif) -- rien n'est mesure ici.")
        return 2
    finally:
        from engine.runner.snapshot import clear_ability_states_cache
        clear_ability_states_cache("build#%s" % rid)
        rpc("disposeRunner", {"runnerId": rid}, 30)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--montage-geo", action="store_true",
                    help="monte le bras `--geo-only` du probe amulette et mesure le selecteur "
                         "PENDANT ce montage (la seule facon de trancher la contradiction)")
    ap.add_argument("--level", type=int, default=6, help="niveau de relique du montage geo")
    ap.add_argument("--state-file", default=None, help="chemin ABSOLU, propre (defaut : temporaire)")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="C3_14")
    ap.add_argument("--origin", default="5,4", help="col,row de l'origine (le PORTEUR)")
    ap.add_argument("--voisin", default="5,3", help="col,row du voisin cherche (le COMPAGNON)")
    ap.add_argument("--roster", type=int, default=3,
                    help="taille des rosters (C3_14 n'a que 4 spawns par camp)")
    a = ap.parse_args()

    if a.montage_geo:
        return montage_geo(a)

    ocol, orow = (int(x) for x in a.origin.split(","))
    vcol, vrow = (int(x) for x in a.voisin.split(","))

    sf = a.state_file
    if sf is None:
        fd, sf = tempfile.mkstemp(prefix="probe_589r1r1r2r1r4_", suffix=".json")
        os.close(fd)
        Path(sf).unlink(missing_ok=True)

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        r = R._rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(sf, a.seed, a.board, a.roster)
    print("runner %s | board %s seed %s | origine (%d,%d) voisin cherche (%d,%d)"
          % (rid, a.board, a.seed, ocol, orow, vcol, vrow))
    try:
        print("")
        print("=== etape 1 -- le capteur repond-il ? ===")
        res = rpc("adjacentTilesNative",
                  {"runnerId": rid,
                   "tiles": [{"col": ocol, "row": orow}, {"col": vcol, "row": vrow}]}, 120)
        if not res.get("ok"):
            raise MontageError("adjacentTilesNative rend ok=false : %s" % res.get("error"))
        diag = res.get("diag") or {}
        print("  diag = %s" % json.dumps(diag, sort_keys=True))
        print("  missing = %s" % (res.get("missing") or []))
        if int(diag.get("calls") or 0) == 0:
            raise MontageError("0 appel natif -- le capteur n'a RIEN mesure (origines : %d)"
                               % int(res.get("originCount") or 0))
        rows = res.get("origins") or []
        if not rows:
            raise MontageError("aucune origine resolue -- les coordonnees demandees n'existent pas")

        print("")
        print("=== etape 2 -- ce que le natif rend, regime par regime ===")
        cible = None
        for r in rows:
            pos = r.get("pos") or {}
            print("  origine id=%s kind=%s pos=(%s,%s)"
                  % (r.get("originId"), r.get("kind"), pos.get("col"), pos.get("row")))
            print("     originTiles  = %s" % (r.get("originTiles"),))
            print("     connectivity = %s" % (r.get("connectivity"),))
            for rn, rv in (r.get("byRegime") or {}).items():
                if "error" in rv:
                    raise MontageError("regime %s en erreur : %s" % (rn, rv["error"]))
                print("     %-8s count=%d : %s" % (rn, rv.get("count", 0), _fmt(rv.get("tiles") or [])))
            if int(pos.get("col", -999)) == ocol and int(pos.get("row", -999)) == orow:
                cible = r
        if cible is None:
            raise MontageError("l'origine (%d,%d) n'est pas dans les lignes rendues" % (ocol, orow))

        print("")
        print("=== etape 3 -- ce que la capture `boardGraph` porte, sur la MEME arete ===")
        bg = rpc("boardGraph", {"runnerId": rid}, 120)
        btiles = bg.get("tiles") or []
        bdiag = bg.get("diag") or bg
        by_id = {t.get("id"): t for t in btiles}
        bo = next((t for t in btiles if t.get("col") == ocol and t.get("row") == orow), None)
        bv = next((t for t in btiles if t.get("col") == vcol and t.get("row") == vrow), None)
        print("  boardGraph.adjUnmapped = %s (tuiles %d)"
              % (bdiag.get("adjUnmapped"), len(btiles)))
        if bo is None or bv is None:
            raise MontageError("boardGraph ne porte pas les deux tuiles demandees")
        vo = [by_id.get(n) for n in (bo.get("neighbours") or [])]
        print("  neighbours de (%d,%d) : %s"
              % (ocol, orow, ", ".join("(%s,%s)" % (t.get("col"), t.get("row"))
                                       for t in vo if t)))
        graph_a_l_arete = bv.get("id") in (bo.get("neighbours") or [])
        conn_o = bo.get("connectivity")
        print("  connectivity de (%d,%d) : %s" % (ocol, orow, conn_o))
        print("  boardGraph porte l'arete (%d,%d)->(%d,%d) : %s"
              % (ocol, orow, vcol, vrow, graph_a_l_arete))

        print("")
        print("=== etape 4 -- VERDICT BINAIRE ===")
        sel = (cible.get("byRegime") or {}).get("selector") or {}
        tiles = sel.get("tiles") or []
        natif_a_l_arete = any(int(t.get("col")) == vcol and int(t.get("row")) == vrow
                              for t in tiles)
        print("  `origins[0].byRegime.selector.tiles` contient (%d,%d) : %s"
              % (vcol, vrow, natif_a_l_arete))
        if natif_a_l_arete and not graph_a_l_arete:
            print("VERDICT : la capture `boardGraph` est INCOMPLETE -- le natif rend l'arete que")
            print("  le graphe du port a perdue. Le correctif est dans le REMAPPING, pas dans le")
            print("  selecteur. `#589-r1-r1-r2-r1-r4` FERMABLE.")
            return 0
        if natif_a_l_arete and graph_a_l_arete:
            print("VERDICT : les DEUX portent l'arete -- la mesure de `case-589` sec.6 (`absente de")
            print("  boardGraph.neighbours ET de connectivity, dans les deux sens`) ne se")
            print("  REPRODUIT PAS sur ce montage. C'est elle qu'il faut reprendre.")
            return 1
        print("VERDICT : le natif ne rend PAS ce voisin par CE chemin (regime `selector`).")
        print("  L'inference de `case-589` sec.6 -- << le natif compte >>, deduite de l'ACTIVITE")
        print("  de l'effet et non d'une enumeration -- est ce qu'il faut reprendre.")
        return 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        if a.state_file is None:
            Path(sf).unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MontageError as e:
        print("MONTAGE : %s" % e)
        sys.exit(2)
