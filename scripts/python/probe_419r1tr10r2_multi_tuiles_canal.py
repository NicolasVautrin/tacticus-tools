"""`#419-r1-tr10-r2` -- le canal MULTI-TUILES existe-t-il cote DECISION ?

CRITERE BINAIRE, enonce AVANT la mesure : la `Scene` que construit `playbook.scene.build_predictor`
(le substrat de TOUS les playbooks de la face DECISION) porte-t-elle, pour une MACHINE OF WAR, les
tuiles de ses pieds AUTRES que la MainTile ? Si oui, `playbook.adjacency.iterate_tiles` les lit et le
port calcule le voisinage NATIF. Si non, le port reste sur la MainTile, et le residu est un trou de
SEEDING -- localise, nommable, pas un trou de logique.

Le natif, lui, itere `IdunBattle.Entities.EntityExtensions$$IterateTiles(entity, state)`. C'est LU
dans `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` :

    inner = this.<+0x20 = origin>.Select(entities);        // TOUTES les tuiles du sujet
    foreach (t in inner)
        foreach (n in battleQuery.<+0x50 IterateAdjacentTiles>(t, false, true, true))
            if (!inner.Contains(n)) result.Add(n);         // ring-1 de CHAQUE pied, MOINS l'empreinte

ETAPES -- et l'attestation vient AVANT le verdict :

  1. ATTESTATION du porteur : la MoW est-elle reellement MULTI-TUILES ? Mesuree sur le canal
     COMBAT (`aiMovableTiles`, dont le natif derive les positions via `GetFeetCount`), la SEULE
     source du harnais qui expose une empreinte. Sans elle, << 1 tuile cote decision >> ne
     prouverait rien : l'unite pourrait etre mono-tuile, et le probe rendrait un faux verdict.
  2. MESURE cote DECISION : ce que le dict d'unite de la `Scene` porte, et ce que
     `adjacency.iterate_tiles` en tire.
  3. VERDICT : canal PRESENT (le port compte le vrai voisinage) ou ABSENT.

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine.playbook import adjacency as adj              # noqa: E402
from engine.playbook import scene as _scene               # noqa: E402


class MontageError(RuntimeError):
    """Le montage n'est pas installe -- on REFUSE de mesurer plutot que de rendre un chiffre."""


def _build(state_file: str, seed: str, board: str, mow: str) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
            "--state-file", state_file, "--p-mow", mow]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError("rl_duel build a echoue (rc=%d) : %s"
                           % (p.returncode, (p.stderr or p.stdout or "")[-800:]))
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU, propre")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--mow", default="adeptExorcist", help="MoW du pool (rl_duel build --list-pool)")
    a = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(a.state_file, a.seed, a.board, a.mow)
    print("runner %s | board %s seed %s | MoW visee %s" % (rid, a.board, a.seed, a.mow))

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 180)
    units = dv.get("units") or []
    mow = next((u for u in units
                if str(u.get("visualId") or "").lower() == a.mow.lower()), None)
    if mow is None:
        raise MontageError("montage NON INSTALLE : %s absente de la vue (vues : %s)"
                           % (a.mow, sorted({str(u.get("visualId")) for u in units})))
    uid = mow.get("id")

    print("")
    print("=== etape 1 -- ATTESTATION : la MoW est-elle multi-tuiles ? ===")
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mrow = next((u for u in (mov.get("units") or []) if u.get("unitId") == uid), None)
    print("  aiMovableTiles pour u%s : cles=%s" % (uid, sorted((mrow or {}).keys())))
    empreinte = None
    for k in ("feet", "feetCount", "tiles", "positions"):
        if mrow and k in mrow:
            empreinte = (k, mrow[k])
            break
    print("  empreinte exposee par le canal COMBAT : %r" % (empreinte,))

    print("")
    print("=== etape 2 -- ce que la Scene de DECISION porte ===")
    sc = _scene.build_predictor(rpc, rid)
    su = next((u for u in (sc.units or ()) if u.get("id") == uid), None)
    if su is None:
        raise MontageError("montage NON INSTALLE : u%s absente de la Scene" % uid)
    print("  uid=%s pos=%s" % (uid, sc.pos(uid)))
    print("  cles du dict d'unite : %s" % sorted(su.keys()))
    print("  cle 'feet' presente : %s   valeur=%r" % ("feet" in su, su.get("feet")))
    tiles = adj.iterate_tiles(sc, uid)
    print("  adjacency.iterate_tiles -> %r  (cardinal %d)" % (tiles, len(tiles)))

    print("")
    print("=== etape 3 -- verdict ===")
    if len(tiles) > 1:
        print("CANAL PRESENT : %d tuiles lues, le voisinage multi-tuiles est calcule par le port."
              % len(tiles))
        return 0
    print("CANAL ABSENT : le port ne connait que la MainTile.")
    print("  `AdjacentTilesSelector$$Select` itere `IterateTiles` (TOUTES les tuiles) -- le port")
    print("  SOUS-ESTIME donc le voisinage d'une unite multi-tuiles. Le mirror EST en place")
    print("  (`engine/playbook/adjacency.py`), il est simplement prive de son entree : aucun RPC ne")
    print("  publie `UnitPosition.Tiles` au-dela de `[0]` (cf. `frida/hooks/.../state.ts`, qui ne")
    print("  projette que la premiere tuile). Point d'ancrage a hooker pour fermer le residu :")
    print("  `IdunBattle.Entities.UnitExtensions$$GetUnitFeet` (ou `EntityExtensions$$IterateTiles`),")
    print("  a publier par unite dans `combatSnapshot`.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MontageError as e:
        print("MONTAGE : %s" % e)
        sys.exit(2)
