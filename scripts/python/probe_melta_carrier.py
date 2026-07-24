"""probe_melta_carrier -- recense les profils de degat portant le trait OnMelta et les
unites spawnables (lineup/npc/summons) qui referencent un tel profil. ASCII only."""
from __future__ import annotations

import json
import sys

import gameconfig as GC


def main() -> None:
    idx = GC._index()
    profiles = idx["damageProfiles"]
    # 1) profils avec trait OnMelta
    melta_profiles = []
    for name, p in profiles.items():
        traits = p.get("Traits") or []
        if "OnMelta" in traits:
            melta_profiles.append(name)
    print("=== damageProfiles avec trait OnMelta ===")
    for n in melta_profiles:
        print("  ", n, "->", json.dumps(profiles[n]))
    melta_set = set(melta_profiles)

    # 2) trouver comment une unite reference un profil : inspecter la structure d'une unite
    #    On scanne recursivement chaque unite a la recherche d'une valeur == un profil Melta.
    def find_profile_refs(obj, path=""):
        hits = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                hits += find_profile_refs(v, path + "." + str(k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                hits += find_profile_refs(v, path + "[" + str(i) + "]")
        elif isinstance(obj, str):
            if obj in melta_set:
                hits.append((path, obj))
        return hits

    print("\n=== unites referencant un profil Melta ===")
    carriers = []
    for kind in ("lineup", "npc", "summons"):
        for uid, u in idx[kind].items():
            refs = find_profile_refs(u)
            if refs:
                nm = u.get("name") or ""
                carriers.append((kind, uid, nm, refs))
    for kind, uid, nm, refs in carriers:
        print("  [%s] %s (%s)" % (kind, uid, nm))
        for path, prof in refs:
            print("       ", path, "=", prof)
    print("\nTOTAL carriers:", len(carriers))

    # 3) globalValue meltaDamageExtraDmgPct
    print("\n=== globalValues melta ===")
    gv = (GC._cfg().get("globalValues") or {})
    for k, v in gv.items():
        if "melta" in k.lower():
            print("  ", k, "=", v)


if __name__ == "__main__":
    main()
