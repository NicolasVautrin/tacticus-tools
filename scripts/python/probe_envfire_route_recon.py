#!/usr/bin/env python
"""Recon OFFLINE (gameconfig) pour la migration du DoT `EnvFireTile` vers la route ABILITY.

Cherche, DANS LE POOL SPAWNABLE, les porteurs des discriminants qui separent
`AttackDamageOperation.execute_direct` (percage/armure SEULS) de la route
`AbilityDamageOperation` (`execute_ability_attack(..., is_attack_damage_op=False)`) :
  (a) BOUCLIER  : ability/passif dont le nom evoque un Shield (absorbe AVANT les PV) ;
  (b) BLOCK     : blockChance/blockDamage de base > 0 ;
  (c) RESILIENT : trait de cap per-coup (`ApplyResilientTraitDamageLimit`, cap = hp-1) ;
  (d) MEMBRES   : nrOfMembers > 1 (group-unit cap, deja porte cote `execute_direct`).
Liste aussi les porteurs d'une attaque normale au profil a trait `OnFire` (le vecteur de POSE
du feu de tuile, `OnFireDamageAbility`). Sortie ASCII only. Usage: python probe_envfire_route_recon.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gameconfig as GC  # noqa: E402

PYDIR = Path(__file__).resolve().parent


def pool_ids() -> list[str]:
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--list-pool"],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = []
    for ln in (p.stdout or "").splitlines():
        s = ln.strip()
        if s and " " not in s and not s.startswith("["):
            out.append(s)
    return out


def _flat(u: dict) -> dict:
    """Aplati les sous-dicts de stats d'une unite gameconfig (les stats de combat ne sont pas
    au top-level)."""
    out = dict(u)
    for k, v in list(u.items()):
        if isinstance(v, dict):
            for k2, v2 in v.items():
                out.setdefault(k2, v2)
    return out


def main() -> int:
    ids = pool_ids()
    print(f"[recon] pool spawnable = {len(ids)} unites")
    res_res, res_block, res_shield, res_grp, res_fire = [], [], [], [], []
    for uid in ids:
        u = GC.unit(uid) or {}
        f = _flat(u)
        traits = set(f.get("traits") or [])
        if "Resilient" in traits:
            res_res.append((uid, sorted(traits), sorted((f.get("passiveAbilities") or []))))
        bc = int(f.get("blockChance") or f.get("BlockChance") or 0)
        if bc > 0:
            res_block.append((uid, bc))
        n = int(f.get("nrOfMembers") or 1)
        if n > 1:
            res_grp.append((uid, n))
        for a in list(f.get("activeAbilities") or []) + list(f.get("passiveAbilities") or []):
            if "shield" in str(a).lower():
                res_shield.append((uid, a))
        # profil de l'arme normale (cle variable selon le dump) -> trait OnFire ?
        for key in ("damageProfile", "DamageProfile", "weaponDamageProfile"):
            pr = f.get(key)
            if pr and "OnFire" in ((GC.damage_profile(str(pr)) or {}).get("Traits") or []):
                res_fire.append((uid, pr))
                break

    print(f"\n[recon] (c) RESILIENT ({len(res_res)}):")
    for uid, tr, pas in res_res:
        print(f"    {uid:24s} traits={tr}")
        print(f"    {'':24s} passifs={pas}")
    print(f"\n[recon] (b) BLOCK base ({len(res_block)}): {sorted(res_block)}")
    print(f"[recon] (a) SHIELD-ability ({len(res_shield)}): {sorted(res_shield)}")
    print(f"[recon] (d) GROUP nrOfMembers>1 ({len(res_grp)}): {sorted(res_grp)}")
    print(f"[recon] arme normale a profil OnFire ({len(res_fire)}): {sorted(res_fire)}")
    print("\n[recon] cles disponibles sur une unite (apres aplatissement) :")
    print(sorted(_flat(GC.unit(ids[0]) or {}).keys()))
    print("\n[recon] adeptRetributor (kit brut) :")
    print(json.dumps(GC.unit("adeptRetributor") or {}, indent=1)[:2500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
