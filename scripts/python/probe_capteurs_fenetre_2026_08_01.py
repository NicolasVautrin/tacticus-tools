"""Verification des TROIS capteurs deployes par la fenetre du 2026-08-01.

Ce probe MESURE, il ne garde rien : il repond a « le capteur repond-il ? », pas a
« la valeur est-elle juste ». Les gardes de justesse appartiennent aux taches qui
consomment les capteurs (#403 pour le fog, #366-r1-effect-targets pour les cibles).

1. `boardGraph[].isInFog`  -- publication du champ deja LU par `match-state.ts`
   (`TileComponent+0x40`), que `FlyPathfinder$$IsValidPathNode` teste avec `!IsWall`.
2. `statOverride`          -- `StatOverrideComponent` de l'entite-effet, jumeau du
   `statMod` deja publie (l'autre canal de `ChangeStat`, parts 7/8).
3. `targetIds`             -- `EffectComponent+0x48`, ecrit par `AddTargetId`, la SORTIE
   native de tout `CreateTargetSelector` d'effet. TRI-ETAT : `None` = pas mesure,
   `[]` = mesure et vide.

Sorties ASCII uniquement (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

HOST = "http://127.0.0.1:8765"


def rpc(sid: int, method: str, body=None, timeout: int = 120):
    """`timeout` en SECONDES cote appelant ; le host attend des MILLISECONDES."""
    payload = json.dumps({"method": method, "args": [body or {}],
                          "timeout": int(timeout) * 1000}).encode()
    req = urllib.request.Request(
        f"{HOST}/api/scripts/{sid}/rpc", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 30) as r:
        out = json.load(r)
    if out.get("error"):
        raise RuntimeError("%s: %s" % (method, str(out["error"])[:300]))
    return out.get("result")


def live_session() -> int:
    with urllib.request.urlopen(f"{HOST}/api/admin/status", timeout=20) as r:
        s = json.load(r).get("session")
    if not s or s.get("status") != "running":
        sys.exit("pas de session Frida vivante")
    return int(s["id"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    a = ap.parse_args()
    sid = live_session()
    rid = a.runner
    ok = True

    # --- 1. isInFog au boardGraph -------------------------------------------
    bg = rpc(sid, "boardGraph", {"runnerId": rid})
    tiles = bg.get("tiles") if isinstance(bg, dict) else None
    if not tiles:
        print("[fog] ECHEC : boardGraph ne rend aucune tuile")
        ok = False
    else:
        with_field = [t for t in tiles if "isInFog" in t]
        n_fog = sum(1 for t in with_field if t.get("isInFog"))
        print(f"[fog] tuiles={len(tiles)} portant isInFog={len(with_field)} "
              f"dont isInFog=true : {n_fog}")
        if len(with_field) != len(tiles):
            print("[fog] ECHEC : le champ n'est pas publie sur toutes les tuiles")
            ok = False

    # --- 2 et 3. statOverride / targetIds sur les effets ---------------------
    # C'est `decisionView` qui porte les effets par unite -- PAS `observeBattle`
    # (dont les lignes d'unite n'ont pas de champ `effects`) ni `combatSnapshot`.
    dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    effs = []
    for u in (dv.get("units") or []):
        for e in (u.get("effects") or []):
            effs.append(e)
    print(f"[effets] entrees d'effet publiees : {len(effs)}")
    if not effs:
        print("[effets] NON MESURE : aucun effet dans cet etat -- le montage "
              "n'exerce pas les deux capteurs (ce n'est PAS un echec du capteur)")
        return 0 if ok else 1

    has_so = sum(1 for e in effs if "statOverride" in e)
    so_nonnull = sum(1 for e in effs if e.get("statOverride"))
    has_ti = sum(1 for e in effs if "targetIds" in e)
    ti_null = sum(1 for e in effs if e.get("targetIds") is None)
    ti_empty = sum(1 for e in effs
                   if isinstance(e.get("targetIds"), list) and not e["targetIds"])
    ti_full = sum(1 for e in effs if e.get("targetIds"))

    print(f"[statOverride] champ present={has_so}/{len(effs)} non-null={so_nonnull}")
    print(f"[targetIds]    champ present={has_ti}/{len(effs)} "
          f"| null(pas mesure)={ti_null} vide={ti_empty} non-vide={ti_full}")

    if has_so != len(effs) or has_ti != len(effs):
        print("ECHEC : un des deux champs n'est pas publie sur tous les effets")
        ok = False
    if ti_null == len(effs):
        print("ATTENTION : targetIds est null PARTOUT -- le champ EffectComponent+0x48 "
              "n'a pas ete resolu par l'enumeration. Capteur MUET, a re-lire.")
        ok = False

    for e in effs[:6]:
        print("   ex:", json.dumps(
            {k: e.get(k) for k in ("effectType", "name", "statMod",
                                   "statOverride", "targetIds")},
            ensure_ascii=True)[:200])

    print("PROBE OK" if ok else "PROBE ROUGE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
