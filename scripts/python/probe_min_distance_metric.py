"""R7 -- `IdunBattleLogic.Entities.DSLFormulas$$MinDistance` mesure-t-il une distance HEX ou une
distance de CHEMIN ? Et le proxy Chebyshev qui le remplace dans le chemin de DEGAT diverge-t-il
du natif sur une configuration ATTEIGNABLE en bataille ?

QUESTION (binaire), et pourquoi elle se posait : le depot AFFIRMAIT LES DEUX.
  * `engine/entities/traits/combat.py` : "Proxy distance (Chebyshev sur coordonnees offset) du
    MinDistance natif (pathfinding)" ;
  * `engine/entities/selectors/units.py` : "`IdunBattleLogic.Entities.DSLFormulas$$MinDistance`
    (distance hex entre MainTiles)".

RE (decompile = verite, gqfc5mff6c) -- chaine LUE, appelant par appelant :

  `IdunBattleLogic.Entities.DSLFormulas$$MinDistance(ctx, selA, selB)` construit une instance de la
  classe `DAT_18324e3c0` en lui passant les DEUX selecteurs (ctor foldé/mislabelé par ghidra en
  `HasUsedActiveAbilityThisTurnTrigger___ctor` -- l'ANCRE fiable est le singleton de classe, pas le
  nom du ctor). Le `Calculate` de cette classe est
  `IdunBattle.Entities.Formulas.MinDistanceFormula$$Calculate` :

      best = int.MaxValue                                  # 0x7fffffff
      foreach a in selector@+0x10.Select(ctx):             # 1er ensemble d'entites
          pa = GetComponent<PositionComponent>(a)
          foreach b in selector@+0x18.Select(ctx):         # 2e ensemble d'entites
              pb = GetComponent<PositionComponent>(b)
              best = Math.Min(best, PositionComponent.Distance(pb, pa))
      return best

  `IdunBattle.Entities.Components.PositionComponent$$Distance(a, b)` :
      `IdunBattle.Utils.Hex.AxialCoordinate$$ToCubeCoordinate` sur CHACUN des deux (le champ
      axial vit a `PositionComponent+0x10`), puis `IdunBattle.Utils.Hex.CubeCoordinate$$Distance`.

  `IdunBattle.Utils.Hex.AxialCoordinate$$ToCubeCoordinate(axial)` -- convention OFFSET explicite,
  choisie par le 3e champ de l'axial (`axial+0x8`, 0 dans `PositionComponent$$.ctor`) :
      off = (flag == 0) ? col + (col & 1) : col & ~1
      x   = col ;  z = row - off / 2 ;  y = -(x + z) ;  cube+0xc = flag
  `IdunBattle.Utils.Hex.CubeCoordinate$$Distance(a, b)` = `Max(Max(|dx|, |dy|), |dz|)`.

=> **AUCUN pathfinding nulle part** : ni graphe, ni file, ni cout de terrain, ni obstacle. C'est de
la geometrie hexagonale PURE, en coordonnees cube, sur la convention offset odd-q -- exactement
`hexgeo.to_cube` / `hexgeo.distance` du depot (`(|dx|+|dy|+|dz|)/2` et `max(|dx|,|dy|,|dz|)` sont
EGAUX sur tout cube valide, ou x+y+z=0).

D'OU VENAIT LA CONFUSION -- deux natifs DISTINCTS aux noms voisins :
  * `IdunBattleLogic.Entities.DSLFormulas$$MinDistance` (noeud DSL)                -> HEX (ci-dessus) ;
  * `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` (utilite IA
    de MOUVEMENT) -> celui-la itere les tuiles du `ClosestEnemy` et demande une ROUTE au service de
    pathfinding, dont il lit la LONGUEUR (`route+0x18`). C'est bien une distance de CHEMIN, et
    `engine/utilities/move.py` a raison de le dire -- mais ce n'est PAS le noeud du DSL.
Le commentaire de `combat.py` avait recopie la glose du SECOND sur le PREMIER.

CE QUE LE PROXY CHEBYSHEV EN FAIT (etape A, offline, sans session) :
  `max(|dcol|, |drow|)` sur coordonnees OFFSET n'est pas la distance hex. Le balayage exhaustif
  montre `hex >= cheby` TOUJOURS (0 violation) : le proxy SOUS-ESTIME, donc sur un gate
  `!(MinDistance > 2)` il OUVRE ce que le natif FERME -- degradation PERMISSIVE, silencieuse.
  Les patrons discriminants dependent de la PARITE de la colonne de depart (asymetrie odd-q).

CE QUE CA CHANGE EN BATAILLE (etape B, live) : le gate
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger` =
`On(8) & AmountIsOdd(CurrentHitIndex()) & OwnerIsCaster & !AmountIsGreater(MinDistance(owner@0x160,
target@0x178), Direct(2))`. Sur une configuration `hex == 3` et `cheby == 2`, le natif FERME le gate
et le port l'OUVRE : le port roule un `Maybe(GetBonusHitChance)` par coup d'index impair, ce qui
DECALE le flux RNG et fait diverger les per-coup. C'est observable BIT-A-BIT, sans dependre du
resultat stochastique du `Maybe` lui-meme.

Discipline runner : state-file UNIQUE en chemin ABSOLU sous logs/, `--board` explicite, dispose en
fin. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import hexgeo

# --------------------------------------------------------------------------- le proxy incrimine

# Copie VERBATIM du proxy tel qu'il etait ecrit dans `engine/entities/traits/combat.py::_cheby` et
# `engine/runner/damage_model.py::_cheby` (le probe doit pouvoir mesurer l'ecart APRES le fix, donc
# il ne peut pas importer une fonction destinee a disparaitre).
def cheby(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


# --------------------------------------------------------------------------- etape A : offline


def sweep_patterns(span: int = 24):
    """Balayage EXHAUSTIF `span x span` : le proxy peut-il jamais SUR-estimer, et quels sont les
    patrons (parite de colonne, dcol, drow) qui font diverger le gate `<= 2` ?

    Rend `(violations, worst_gap, patterns)` ou `patterns` = set de (parite_col, dcol, drow, hex)."""
    violations, worst, patterns = [], 0, set()
    for c1 in range(span):
        for r1 in range(span):
            for c2 in range(span):
                for r2 in range(span):
                    a, b = (c1, r1), (c2, r2)
                    h, k = hexgeo.distance(a, b), cheby(a, b)
                    if h < k:
                        violations.append((a, b, h, k))
                    worst = max(worst, h - k)
                    if k <= 2 < h:
                        patterns.add((c1 & 1, c2 - c1, r2 - r1, h))
    return violations, worst, patterns


def _load_board_tiles(path):
    """Tuiles JOUABLES `(col, row)` d'un board de `data/boards/` (format `board.Tiles[col].Tile[row]`)."""
    with open(path, encoding="utf-8") as fh:
        b = (json.load(fh) or {}).get("board") or {}
    out = []
    for col, colobj in enumerate(b.get("Tiles") or []):
        for row, t in enumerate((colobj or {}).get("Tile") or []):
            if t and not t.get("ForceUnplayable") and t.get("TileId") != "Block":
                out.append((col, row))
    return out, int(b.get("Width") or 0), int(b.get("Height") or 0)


def sweep_board(path, gate: int = 2):
    """Sur un board REEL : quelle fraction des paires de tuiles jouables le gate `<= gate` classe-t-il
    DIFFEREMMENT selon la metrique ? Rend un dict de comptes."""
    tiles, w, h = _load_board_tiles(path)
    n_pairs = n_dist_diff = n_gate_diff = 0
    examples = []
    for i, a in enumerate(tiles):
        for b in tiles[i + 1:]:
            n_pairs += 1
            dh, dk = hexgeo.distance(a, b), cheby(a, b)
            if dh != dk:
                n_dist_diff += 1
            if (dh <= gate) != (dk <= gate):
                n_gate_diff += 1
                if len(examples) < 8:
                    examples.append((a, b, dh, dk))
    return {"board": os.path.basename(path), "w": w, "h": h, "tiles": len(tiles),
            "pairs": n_pairs, "dist_diff": n_dist_diff, "gate_diff": n_gate_diff,
            "examples": examples}


def run_offline(board_path=None, span=24):
    viol, worst, pats = sweep_patterns(span)
    print("== ETAPE A -- metrique, offline (aucune session) ==")
    print("balayage exhaustif %dx%d : violations de `hex >= cheby` = %d" % (span, span, len(viol)))
    print("  -> le proxy SOUS-ESTIME toujours : sur `!(MinDistance > 2)` il OUVRE ce que le natif FERME")
    print("ecart max hex - cheby sur la fenetre : %d (l'erreur n'est bornee par AUCUNE constante)" % worst)
    print("patrons discriminants du gate <= 2 : %d" % len(pats))
    for p in sorted(pats):
        print("   parite_col_depart=%d dcol=%+d drow=%+d -> hex=%d cheby=%d"
              % (p[0], p[1], p[2], p[3], max(abs(p[1]), abs(p[2]))))
    if board_path:
        s = sweep_board(board_path)
        print("board REEL %s (%dx%d, %d tuiles jouables) :" % (s["board"], s["w"], s["h"], s["tiles"]))
        print("   paires=%d  distances differentes=%d (%.1f%%)  gate <=2 DIVERGENT=%d (%.2f%%)"
              % (s["pairs"], s["dist_diff"], 100.0 * s["dist_diff"] / max(1, s["pairs"]),
                 s["gate_diff"], 100.0 * s["gate_diff"] / max(1, s["pairs"])))
        for a, b, dh, dk in s["examples"]:
            print("   ex. %s -> %s : hex=%d cheby=%d (natif FERME, proxy OUVRE)" % (a, b, dh, dk))
    return len(viol), worst, pats


# --------------------------------------------------------------------------- etape B : live

# Le montage live reutilise INTEGRALEMENT le harnais R6-b'' (meme porteur, meme ability, meme
# regime percage-dominant) et n'en change QUE le predicat de position : la ou `_want_far` exigeait
# `cheby >= 3` pour NEUTRALISER l'ecart de metrique, `_want_split` exige `cheby <= 2` pour l'EXPOSER.

DAKKA_CARRIER = "orksKillaKan"     # Hero + GetStuckIn + ability OFFENSIVE 6 coups (3 index impairs)
DAKKA_ABILITY = 1171               # ActiveAbilityType.DakkaDakkaDakka -- portee 3 hex
DAKKA_TARGET = "ultraApothecary"


def want_split(hexdist, cheb):
    """CONFIGURATION DISCRIMINANTE : `MinDistance` natif == 3 (gate FERME) mais proxy cheby <= 2
    (gate OUVERT). C'est le seul predicat de position qui separe les deux modeles ; la portee 3 de
    `DakkaDakkaDakka` la rend castable."""
    return hexdist == 3 and cheb <= 2


def want_witness(hexdist, cheb):
    """TEMOIN : cible ADJACENTE -- les DEUX metriques valent 1, donc les deux modeles ouvrent le
    gate. Ce montage doit rester BIT-EXACT de part et d'autre du fix ; sans lui, un lot ou les deux
    hypotheses coincident ne conclurait rien."""
    return hexdist == 1 and cheb == 1


def measure_split(rpc, rid, board, label, want, seed):
    """UN montage : AMENE le porteur a la configuration voulue (DEPLACE -- jamais « bloque par la
    geometrie de spawn »), caste `DakkaDakkaDakka` LIVE, rejoue le MEME cast offline sous les
    quatre modeles de `VARIANTS`, et confronte.

    Le PIEGE de harnais (`applyAction` peut rendre `ok=True` SANS rien muter) est garde par
    `live_hits_of_attacker`, qui FILTRE sur `Attacker_Id` + `Target_Id` : un cast no-op rend une
    liste VIDE, jamais une divergence geante silencieuse -- on le teste explicitement."""
    from probe_r6bp2_after_hit_maybe_ability import _drive_ability, _replay_dakka, _confront
    from probe_r6bp_after_hit_maybe_groups import live_hits_of_attacker
    cid, tid, moved = _drive_ability(rpc, rid, board, DAKKA_CARRIER, DAKKA_TARGET,
                                     DAKKA_ABILITY, want)
    if cid is None:
        print("[%s] configuration voulue NON atteinte" % label)
        return None
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
    tu = next((u for u in (dv.get("units") or []) if u.get("id") == tid), {})
    cpos = (cu.get("pos", {}).get("col"), cu.get("pos", {}).get("row"))
    tpos = (tu.get("pos", {}).get("col"), tu.get("pos", {}).get("row"))
    print("[%s] caster=%s cible=%s -> hexgeo=%d cheby=%d"
          % (label, cpos, tpos, hexgeo.distance(cpos, tpos), cheby(cpos, tpos)))
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": DAKKA_ABILITY}, "captureEvents": True}, 120)
    live, dirty, srcs = live_hits_of_attacker(res, tid, cid)
    if not live:
        print("[%s] AUCUN event de degat live -- cast NO-OP, mesure ABANDONNEE (piege de harnais)"
              % label)
        return None
    if dirty:
        print("[%s] coup non propre (crit/block/evade) -- mesure ABANDONNEE" % label)
        return None
    off, params = _replay_dakka(dv, ob, snap, board, rng0, cid, tid, moved)
    if off is None:
        print("[%s] parametres offline indisponibles" % label)
        return None
    return _confront(label, seed, live, srcs, off, params)


def run_live(seed, board_id, armor=6000):
    """Monte UNE bataille et y joue les DEUX montages : le DISCRIMINANT (`split`) et le TEMOIN
    (`witness`). Un lot ou les deux hypotheses donnent le meme resultat ne conclurait rien -- le
    temoin est ce qui rend le discriminant lisible."""
    from probe_r6_round_materialize import _build, _mkrpc
    from engine.entities.pathfinding.board import Board

    rpc = _mkrpc()
    out = {}
    for label, want in (("split", want_split), ("witness", want_witness)):
        rid = None
        try:
            rid, _sf = _build(seed, DAKKA_CARRIER, DAKKA_TARGET,
                              extra=["--crit", "0,0", "--block-target", "0,0",
                                     "--armor-target", str(armor), "--board", board_id])
            if rid is None:
                print("[%s] build KO" % label)
                continue
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="native_sym")
            out[label] = measure_split(rpc, rid, board, label, want, seed)
        finally:
            if rid is not None:
                rpc("disposeRunner", {"runnerId": rid}, 60)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["offline", "live", "both"], default="offline")
    ap.add_argument("--board-file", default=None, help="chemin d'un board de data/boards/")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--span", type=int, default=24)
    a = ap.parse_args()
    if a.stage in ("offline", "both"):
        run_offline(a.board_file, a.span)
    if a.stage in ("live", "both"):
        run_live(a.seed, a.board)
    return 0


if __name__ == "__main__":
    sys.exit(main())
