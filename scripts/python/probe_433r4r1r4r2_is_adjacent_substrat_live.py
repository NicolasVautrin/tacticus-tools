"""#433-r4-r1-r4-r2 -- `battle_query.is_adjacent` : GEOMETRIE+porte contre la liste STOCKEE.

LE CRITERE, pose AVANT la methode
---------------------------------
`engine/battle_query.py::is_adjacent` mirroir
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, qui itere la
liste STOCKEE du `ConnectivityComponent` puis applique `|delev| < 2`. Le port, lui, recalcule la
couronne hex (`hexgeo.distance == 1`) et applique la meme porte. Trois questions BINAIRES, dans
cet ordre -- la 2e decide s'il FAUT basculer, la 1re si on PEUT :

  Q1. Basculer sur la liste stockee introduit-il de l'ASYMETRIE ?  (le port geometrique est
      symetrique par construction ; la liste, elle, est un champ capte)
  Q2. Quel est le SOLDE du basculement, arete par arete et PAR SENS ?
  Q3. Le gisement est-il un artefact d'UN board ?

LE DISCRIMINANT (leçon de #589-r1) : on compare les DEUX SUBSTRATS DIRECTEMENT -- `G_gated`
contre `N` -- jamais un critere qui melange une 3e vue. Les couples ou seule la porte differe
noient le cas utile.

LES TROIS VUES, et leur relation LUE au decompile (pas supposee) :

    G = couronne hex even-q recalculee        (`Board.neighbours_geometric`)
    C = `connectivity`   = `ConnectivityComponent` BRUT, aucune elevation
    N = `neighbours`     = `BattleQuery$$GetAdjacentTiles(t, 0, 0, 1)` = C INTERSECTE {|delev| < 2}

    G_gated = G INTERSECTE {|delev| < 2}      <- CE QUE LE PORT FAIT AUJOURD'HUI
    N                                          <- CE QUE LE NATIF FAIT

  `N subset C subset G` (#584) ==> `N subset G_gated`, donc l'ecart est PUREMENT PERMISSIF et
  vaut exactement `(G \\ C) INTERSECTE {|delev| < 2}`. Le probe le MESURE au lieu de le deduire :
  un `N \\ G_gated` non nul rougirait et dirait que la relation d'inclusion est fausse.

POURQUOI L'ASYMETRIE N'EST PAS UNE OPINION -- `IdunBattle.Operations.InitializeConnectivityOperation$$Execute`
construit la liste par le critere

    A -> B  ssi  HasEdge(A, e) ET B = NeighbourAt(A, e) existe sur le plateau
                 ET HasEdge(B, (e + 3) % 6)

(`IdunBattle.Entities.Components.TileComponent$$HasEdge` sur LES DEUX tuiles ;
`IdunBattle.Operations.AddTileOperation$$RotateTileEdges` fixe le modulo a **6**, donc
`opp(e) = (e+3) % 6` est une INVOLUTION). Le critere est donc SYMETRIQUE par construction, et la
porte `|delev| < 2` l'est aussi (valeur absolue). `ConnectTeleportTiles` n'ecrit que
`ConnectivityComponent+0x18` (le jumeau de teleport), jamais la liste `+0x10`, et il l'ecrit
**dans les deux sens**. ==> l'asymetrie attendue est **ZERO**, et une mesure non nulle
accuserait le CAPTEUR, pas le natif.

Usage (session warmee) :
    python probe_433r4r1r4r2_is_adjacent_substrat_live.py                 # les 4 boards
    python probe_433r4r1r4r2_is_adjacent_substrat_live.py --board C1_74
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
LOGSDIR = ROOT / "logs"
sys.path.insert(0, str(PYDIR))

# `C1_74` porte les 2 `Bridge` du residu (les 4 aretes) ; `C3_14` en porte 15 (amplitude, cf.
# case-589-r1) ; `MC1_67` est l'arene de reference ; `C6_25` est le temoin sans `Bridge`.
BOARDS = ("C1_74", "C3_14", "MC1_67", "C6_25")


def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=180):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int) -> tuple[int, pathlib.Path]:
    """Le graphe de tuiles est STATIQUE : le compte d'unites n'influe sur AUCUNE des vues
    mesurees ici. On DEGRADE donc le roster plutot que d'echouer quand un board a peu de
    spawns joueur (meme parade que `probe_448r1r1r1r1r2`)."""
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p433r4r1r4r2_state_%s.json" % board)
    p = None
    for roster in (5, 4, 3, 2, 1):
        state_file.unlink(missing_ok=True)
        cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
               "--board", board, "--no-ai", "--roster", str(roster),
               "--state-file", str(state_file)]
        p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state_file.exists():
            return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), state_file
        if "spawns joueur <" not in ((p.stdout or "") + (p.stderr or "")):
            break
    sys.stdout.write(((p.stdout if p else "") or "")[-1500:])
    sys.stdout.write(((p.stderr if p else "") or "")[-1500:])
    raise SystemExit("build KO (%s)" % board)


def _vues(res: dict):
    """Les trois vues comme ENSEMBLES D'ARETES DIRIGEES, plus `G_gated`.

    Tri-etat respecte : une tuile dont `connectivity` est `None` n'entre pas dans `C` (elle est
    comptee a part). Les arcs pointant hors de la capture sont ecartes des DEUX cotes -- sinon
    l'asymetrie mesurerait le bord de la capture au lieu du graphe."""
    from engine.entities.pathfinding.board import Board

    tiles = res.get("tiles") or []
    by_id = {t["id"]: t for t in tiles}
    bd = Board(tiles)
    elev = {t["id"]: int(t.get("elevation") or 0) for t in tiles}
    G, N, C = set(), set(), set()
    sans_composant = []
    for t in tiles:
        tid = t["id"]
        for nid in bd.neighbours_geometric(tid):
            if nid in by_id:
                G.add((tid, nid))
        for nid in (t.get("neighbours") or []):
            if nid in by_id:
                N.add((tid, nid))
        conn = t.get("connectivity")
        if conn is None:
            sans_composant.append(tid)
            continue
        for nid in conn:
            if nid in by_id:
                C.add((tid, nid))
    G_gated = {(a, b) for (a, b) in G if abs(elev[a] - elev[b]) < 2}
    return by_id, elev, G, N, C, G_gated, sans_composant


def _confronter_port(res: dict, N: set) -> tuple[int, int]:
    """Joue le CODE LIVRE sur toutes les paires de tuiles et compte ses desaccords avec `N`.

    Le canal ne lui est PAS passe a la main : il est derive comme en production, par la `Scene`
    (`Scene.neigh_by_pos` -> `adjacent_neigh_by_pos`) puis lu par `battle_query.neigh_map`. C'est
    donc le CABLAGE qui est confronte, pas seulement la primitive.

    Rend `(desaccords avec canal, desaccords sans canal)` -- le second est le CONTRE-BRAS."""
    from engine import battle_query as bq
    from engine.entities.pathfinding.board import Board
    from engine.playbook.scene import Scene

    tiles = res.get("tiles") or []
    bd = Board(tiles)
    sc = Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
               vis_by_id={}, units=[], hp_by_id={}, pos_by_id={}, team_by_id={}, eff_state=None,
               elev_by_pos=bd.elev_by_pos(), board=bd)
    canal = bq.neigh_map(sc)
    pos_of = {t["id"]: (t["col"], t["row"]) for t in tiles}
    vrai = {(pos_of[a], pos_of[b]) for (a, b) in N}
    avec = sans = 0
    for a in pos_of.values():
        for b in pos_of.values():
            if a == b:
                continue
            attendu = (a, b) in vrai
            if bq.is_adjacent(a, b, sc.elev_by_pos, canal) != attendu:
                avec += 1
            if bq.is_adjacent(a, b, sc.elev_by_pos, None) != attendu:
                sans += 1
    return avec, sans


def _asym(edges: set) -> list:
    """Les aretes DIRIGEES sans reciproque -- la question Q1, mesuree et non supposee."""
    return sorted(e for e in edges if (e[1], e[0]) not in edges)


def _fmt(by_id, elev, a, b) -> str:
    def one(x):
        t = by_id.get(x) or {}
        return "(%s,%s)e%s%s" % (t.get("col"), t.get("row"), t.get("elevation"),
                                 "/W" if t.get("isWall") else "")
    return "%s -> %s |delev|=%d  terrain %s -> %s" % (
        one(a), one(b), abs(elev.get(a, 0) - elev.get(b, 0)),
        (by_id.get(a) or {}).get("tileDefId"), (by_id.get(b) or {}).get("tileDefId"))


def run_board(sid, rpc, board: str, seed: int, verbose: bool) -> tuple[int, dict]:
    rid, state_file = _build(board, seed)
    bad = 0
    try:
        res = rpc(sid, "boardGraph", {"runnerId": rid}, 180)
        if not res.get("ok"):
            print("  boardGraph KO: %s" % res.get("error"))
            return 1, {}
        (LOGSDIR / ("p433r4r1r4r2_boardgraph_%s.json" % board)).write_text(
            json.dumps(res), encoding="utf-8")
        by_id, elev, G, N, C, Gg, sans = _vues(res)
        print("  tuiles=%d  |G|=%d  |C|=%d  |N|=%d  |G_gated|=%d  sans composant=%d"
              % (len(by_id), len(G), len(C), len(N), len(Gg), len(sans)))
        if sans:
            print("      ECART: %d tuile(s) sans `connectivity` -- vues C non interpretables"
                  % len(sans))
            bad += 1

        # --- Q1 : l'ASYMETRIE. Attendu 0 partout (le critere natif est symetrique -- cf. l'en-tete).
        aG, aN, aC = _asym(G), _asym(N), _asym(C)
        print("  [Q1] aretes ONE-WAY :  G=%d  C=%d  N=%d   (attendu 0 pour les trois)"
              % (len(aG), len(aC), len(aN)))
        for lbl, lst in (("C", aC), ("N", aN), ("G", aG)):
            if lst:
                bad += 1
                for (a, b) in lst[:12]:
                    print("        %s one-way %s" % (lbl, _fmt(by_id, elev, a, b)))

        # --- Q2 : le SOLDE du basculement `G_gated -> N`, VENTILE PAR SENS.
        #     PERMISSIF  = le port dit VRAI la ou le natif dit FAUX  -> `G_gated \ N`
        #     RESTRICTIF = le port dit FAUX la ou le natif dit VRAI  -> `N \ G_gated`
        perm = sorted(Gg - N)
        restr = sorted(N - Gg)
        print("  [Q2] basculement G_gated -> N :  ferme %d arete(s) PERMISSIVE(s) ; "
              "en ouvre %d RESTRICTIVE(s)" % (len(perm), len(restr)))
        if restr:
            # `N subset C subset G` (#584) rend ce cas IMPOSSIBLE : un non-zero refute
            # l'inclusion, donc le basculement ne serait plus un gain net.
            print("      ECART: N \\ G_gated non vide -- l'inclusion N subset G_gated est FAUSSE")
            bad += 1
            for (a, b) in restr[:12]:
                print("        RESTRICTIF %s" % _fmt(by_id, elev, a, b))
        for (a, b) in perm[:16]:
            print("        PERMISSIF %s" % _fmt(by_id, elev, a, b))
        # Le permissif doit se lire ENTIEREMENT comme « HasEdge refuse » : `(G \ C) ^ gate`.
        attendu = {(a, b) for (a, b) in (G - C) if abs(elev[a] - elev[b]) < 2}
        if not sans and set(perm) != attendu:
            print("      ECART: le permissif (%d) != (G\\C) gate (%d) -- une 3e cause coexiste"
                  % (len(perm), len(attendu)))
            bad += 1

        # --- symetrie du GISEMENT : si les aretes fermees vont par paires, le basculement ne
        #     peut pas creer d'incoherence de verdict entre `is_adjacent(a,b)` et `(b,a)`.
        perm_asym = [e for e in perm if (e[1], e[0]) not in set(perm)]
        print("  [Q2b] aretes permissives sans leur reciproque : %d (attendu 0)" % len(perm_asym))
        if perm_asym:
            bad += 1
            for (a, b) in perm_asym[:12]:
                print("        %s" % _fmt(by_id, elev, a, b))

        # --- Q3 : le CODE LIVRE, pas seulement les ensembles. On joue `battle_query.is_adjacent`
        #     sur toutes les paires, a travers le CABLAGE reel (`Scene` -> `neigh_map` -> foyer),
        #     et on le confronte a la verite native `N`. Le contre-bras (canal neutralise) est
        #     OBLIGATOIRE : sans lui, un accord ne prouverait pas que le canal MORD.
        n_avec, n_sans = _confronter_port(res, N)
        print("  [Q3] port AVEC canal : %d desaccord(s) vs natif (attendu 0)" % n_avec)
        print("       port SANS canal : %d desaccord(s) vs natif (= le gisement ferme)" % n_sans)
        if n_avec:
            bad += 1
        if n_sans != len(perm):
            print("      ECART: le contre-bras (%d) != le gisement mesure (%d)" % (n_sans, len(perm)))
            bad += 1
        return bad, {"tiles": len(by_id), "perm": len(perm), "restr": len(restr),
                     "port_avec": n_avec, "port_sans": n_sans,
                     "asymN": len(aN), "asymC": len(aC), "asymG": len(aG),
                     "GmoinsC": len(G - C) if not sans else None}
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", action="append", default=None)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    boards = a.board or list(BOARDS)
    sid, rpc = _rpc_factory()
    print("== #433-r4-r1-r4-r2 -- `is_adjacent` : geometrie+porte contre la liste STOCKEE")
    print("   session=%s boards=%s seed=%d" % (sid, ",".join(boards), a.seed))
    bad, resume = 0, {}
    for b in boards:
        print("\n-- board %s" % b)
        n, r = run_board(sid, rpc, b, a.seed, a.verbose)
        bad += n
        resume[b] = r
    print("\n== RESUME")
    for b, r in resume.items():
        print("   %-8s tuiles=%s  PERMISSIF=%s RESTRICTIF=%s  one-way N/C/G=%s/%s/%s  "
              "port avec/sans canal=%s/%s"
              % (b, r.get("tiles"), r.get("perm"), r.get("restr"), r.get("asymN"),
                 r.get("asymC"), r.get("asymG"), r.get("port_avec"), r.get("port_sans")))
    # Le gisement doit etre NON NUL quelque part : sinon la mesure est DEGENERE (les deux
    # substrats coincident sur ces boards) et ne dit rien du basculement.
    non_degenere = any((r.get("perm") or 0) > 0 for r in resume.values())
    print("   regime non degenere (au moins un board a un ecart PERMISSIF) : %s"
          % ("OUI" if non_degenere else "NON -- accord DEGENERE, rien a conclure"))
    if not non_degenere:
        bad += 1
    print("VERDICT: %s (%d ecart(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
