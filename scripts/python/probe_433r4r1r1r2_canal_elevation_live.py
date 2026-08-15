#!/usr/bin/env python
"""#433-r4-r1-r1-r2 -- LE REGIME « ELEVATION NON CAPTEE » EXISTE-T-IL LIVE ?

Les deux contrats de port pour une candidate de fat-line dont l'elevation est INCONNUE :

  * `battle_query::is_target_tile_obscured` (fork v1) : la candidate est RETIREE de la liste, donc
    la paire retombe sur la regle « ligne droite » (une seule candidate suffit a bloquer) ;
  * `services/line_of_sight::_determine_blocking_tiles` (foyer complet, mirror de
    `MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingTiles`) : l'inconnue est
    traitee comme `StateExtensions$$GetTileAt -> null`, donc `blk = false`, donc l'ET de la fat-line
    ECHOUE et la paire n'est PAS bloquee.

Le natif n'a AUCUN etat « elevation inconnue » (`TileExtensions$$GetElevationDifference` deref et
leve). Le regime est donc une notion strictement PORT. Ce probe MESURE s'il peut seulement se
produire : il lit le `boardGraph` du runner et compte les tuiles dont le champ `elevation` manque.

Usage : python probe_433r4r1r1r2_canal_elevation_live.py --state-file <absolu> [--runner N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--runner", type=int, default=None)
    args = ap.parse_args()

    rid = args.runner
    if rid is None:
        st = json.load(open(args.state_file, encoding="utf-8"))
        rid = st.get("runnerId") or (st.get("runner") or {}).get("id")
    if rid is None:
        print("PAS MESURE : aucun runnerId (ni --runner ni state-file)")
        return 2

    sid = _resolve_session()
    bg = _rpc(sid, "boardGraph", [{"runnerId": int(rid)}], 60)
    tiles = bg.get("tiles") or []
    if not tiles:
        print("PAS MESURE : le canal `boardGraph` n'a rendu aucune tuile")
        return 2

    sans_elev = [t for t in tiles if t.get("elevation") is None]
    sans_wall = [t for t in tiles if t.get("isWall") is None]
    print("boardGraph : %d tuiles" % len(tiles))
    print("  SANS `elevation` : %d" % len(sans_elev))
    print("  SANS `isWall`    : %d" % len(sans_wall))
    if sans_elev:
        print("  exemples : %s" % [(t.get("col"), t.get("row")) for t in sans_elev[:8]])
    murs = [t for t in tiles if t.get("isWall")]
    print("  MURS (`isWall` vrai) : %d" % len(murs))
    if murs:
        print("  exemples : %s" % [(t.get("col"), t.get("row")) for t in murs[:8]])
    elevs = sorted({t.get("elevation") for t in tiles if t.get("elevation") is not None})
    print("  elevations distinctes : %s" % elevs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
