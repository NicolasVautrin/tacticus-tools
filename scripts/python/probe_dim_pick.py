"""Selection de porteurs/attaquants pour la validation adversariale de Diminutive (#75).

Liste, pour chaque unite du POOL SPAWNABLE (rank donne), le nb de coups melee/ranged de l'arme
et ses abilities -- pour CHOISIR (pas seed-hunter) les attaquants qui exercent :
  - une attaque a 1 SEUL coup (plancher min=1 du canal hits),
  - des attaques multi-coups melee ET ranged autres que celles deja utilisees par l'auteur,
  - des abilities d'attaque (canal ability, pas seulement l'attaque normale).
ASCII only.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
import gameconfig as GC  # noqa: E402
import unit_map as UM  # noqa: E402


def main() -> int:
    pool = sys.argv[1:] if len(sys.argv) > 1 else []
    if not pool:
        print("usage: probe_dim_pick.py <unitId> [<unitId> ...]")
        return 2
    for uid in pool:
        try:
            k = UM.kit(uid) if hasattr(UM, "kit") else None
        except Exception as exc:  # noqa: BLE001
            print(f"{uid}: ERR {exc}")
            continue
        if k is None:
            print(f"{uid}: pas de kit")
            continue
        w = k.get("weapons") or []
        wtxt = ",".join(f"{x.get('hits')}h{'m' if x.get('melee') else 'R'}p{x.get('pierce')}"
                        f"/{x.get('profile')}" for x in w)
        print("%-22s mh=%-3s rh=%-3s [%s] ab=%s" % (
            uid, k.get("melee_hits"), k.get("ranged_hits"), wtxt,
            ",".join(k.get("abilities") or [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
