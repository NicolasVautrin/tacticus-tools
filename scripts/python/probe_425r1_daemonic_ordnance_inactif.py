"""#425-r1 -- le gisement << effet de tuile POSE-mais-INACTIF >>, mesure sur le porteur NOMME.

    python scripts/python/probe_425r1_daemonic_ordnance_inactif.py --runner <id>

CE QUE CE PROBE MESURE, ET POURQUOI IL EXISTE
----------------------------------------------
`IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` itere
`EffectsOwnedComponent.ActiveEffectIds` de la MainTile SANS aucun gate sur `IsActive` ni `Removed`
(relu, et sur DEUX corps -- l'autre etant `DespoiledGroundUtility.<...>d__5`). Le port, lui,
demandait `tileMeta` sans `includeInactive`. Le gisement se ferme par << un montage portant un
effet de tuile dont l'`ActiveCondition` est fausse tout en restant dans la liste possedee >>, et la
fiche nommait le candidat : la zone NON MARCHABLE de `1148 DaemonicOrdnance` (#368).

⚠ **LE `BLOCAGE: porteur` EST REFUTE PAR LE POOL.** `blackForgefiend`, seul porteur non-npc de
`1148`, est dans les **8 MoW spawnables** de `rl_duel build --list-pool` : le montage ne demande
NI injection catalogue NI greffe -- `--p-mow blackForgefiend`, un tour d'attente (la MoW ouvre
`hasAction=False`), puis `act ability --caster <mow> --ability 1148 --to <col,row>`.

Ce probe prend un runner DEJA monte (`--runner`) et croise, tuile par tuile :
  * `tileMeta` DEFAUT (le canal que le port demandait avant #425-r1) ;
  * `tileMeta {includeInactive: true}` (la liste POSSEDEE, celle que le natif itere).
La difference EST le gisement. Il imprime aussi le drapeau `active` par effet, ce qui distingue
<< aucun effet inactif >> de << le capteur n'en publie pas >>.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402


def _noms(tm):
    # `_rpc` rend l'enveloppe `{"result": {...}}` -- la deplier est ce qui separe << 0 tuile >>
    # de << 0 tuile MESUREE >>.
    tm = tm.get("result", tm) if isinstance(tm, dict) else {}
    out = {}
    for t in (tm.get("tiles") or []):
        eff = [(e.get("name"), e.get("active"), e.get("effectType"))
               for e in (t.get("effects") or []) if e.get("name")]
        if eff:
            out[(t.get("col"), t.get("row"))] = sorted(eff)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", required=True)
    a = ap.parse_args()
    sid = _resolve_session()
    if not sid:
        print("PAS MESURE : aucune session Frida")
        return 99
    # ⚠ `runnerId` est un ENTIER cote host : passer la chaine rend `tiles: []` SANS ERREUR --
    # un zero qui se lirait comme une mesure. Mesure du 2026-08-15 : 0 tuile publiee.
    rid = int(a.runner)
    tm_def = _rpc(sid, "tileMeta", {"runnerId": rid}, 90)
    tm_inc = _rpc(sid, "tileMeta", {"runnerId": rid, "includeInactive": True}, 90)
    d_def, d_inc = _noms(tm_def), _noms(tm_inc)
    # ⚠ Le canal DEFAUT ne publie PAS le champ `active` (mesure du 2026-08-15 : la cle est absente,
    # pas `True`). Comparer les TRIPLETS ferait donc rougir les 8 tuiles pour une difference de
    # FORME, pas de contenu -- un faux gisement. Le gisement est un ecart d'ENSEMBLE DE NOMS.
    n_def = {p: sorted(e[0] for e in v) for p, v in d_def.items()}
    n_inc = {p: sorted(e[0] for e in v) for p, v in d_inc.items()}
    print("tuiles publiees : defaut=%d  includeInactive=%d"
          % (len((tm_def.get("result") or {}).get("tiles") or []),
             len((tm_inc.get("result") or {}).get("tiles") or [])))
    print("tuiles PORTANT au moins un effet : defaut=%d  includeInactive=%d"
          % (len(d_def), len(d_inc)))
    for p in sorted(d_inc):
        marque = "" if n_def.get(p) == n_inc[p] else "   <== DIFFERE"
        print("  %s : %s%s" % (p, d_inc[p], marque))
    ecart = {p: v for p, v in n_inc.items() if n_def.get(p) != v}
    print("\nGISEMENT (noms visibles SEULEMENT sous includeInactive) : %s"
          % (ecart or "AUCUN sur ce montage"))
    inactifs = [(p, e) for p, v in d_inc.items() for e in v if e[1] is False]
    print("effets a `active == False` publies : %s" % (inactifs or "aucun"))
    sans_flag = [(p, e[0]) for p, v in d_def.items() for e in v if e[1] is None]
    print("effets SANS champ `active` dans le canal DEFAUT : %d  (absence de mesure, pas un False)"
          % len(sans_flag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
