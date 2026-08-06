"""Recon de CONFRONTABILITE pour #477-r37 -- jetable.

Repond a UNE question par face restante : quel MOVER franchit son gate, et quel PORTEUR arrive en
bataille ? Aucun verdict ici, uniquement des mesures derivees du gameconfig et du pool.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import gameconfig as gc  # noqa: E402


def pool() -> list:
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--list-pool"], cwd=str(PYDIR),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [l.strip() for l in (p.stdout or "").splitlines() if l.startswith("   ") and l.strip()]


def main() -> int:
    idx = gc._index()
    allu = {}
    for kind in ("lineup", "npc", "summons"):
        for uid, u in idx[kind].items():
            allu[uid] = dict(u, kind=kind, id=uid)
    pl = set(pool())
    print("[recon] pool = %d unites ; gameconfig = %d unites (lineup %d / npc %d / summons %d)"
          % (len(pl), len(allu), len(idx["lineup"]), len(idx["npc"]), len(idx["summons"])))

    sample = allu.get("admecMarshall") or next(iter(allu.values()))
    print("[recon] cles d'une entree unite : %s" % sorted(sample.keys()))

    def traits_of(u):
        return [str(x) for x in (u.get("traits") or [])]

    def fac(u):
        return str(u.get("faction") or u.get("factionId") or "")

    # --- 1. faction LeaguesOfVotann (PurgeResponse 1526) ------------------------------------
    factions = sorted({fac(u) for u in allu.values()})
    print("[recon] factions vues (%d) : %s" % (len(factions), factions))
    votann = [uid for uid, u in allu.items()
              if "votann" in fac(u).lower() or "votan" in uid.lower()]
    print("[recon] unites Votann (%d) :" % len(votann))
    for uid in sorted(votann):
        u = allu[uid]
        print("   %-28s kind=%-8s faction=%-20s pool=%s traits=%s"
              % (uid, u["kind"], fac(u), uid in pl, traits_of(u)))

    # --- 2. trait Summon (MawClaws 1469) -----------------------------------------------------
    summon_units = [uid for uid, u in allu.items() if "Summon" in traits_of(u)]
    print("[recon] unites portant le trait Summon : %d ; au pool : %s"
          % (len(summon_units), sorted([u for u in summon_units if u in pl])))
    par_kind = {}
    for uid in summon_units:
        par_kind.setdefault(allu[uid]["kind"], []).append(uid)
    for k, v in sorted(par_kind.items()):
        print("   kind=%-8s : %d" % (k, len(v)))

    # --- 3. HaywireMine (1531) ---------------------------------------------------------------
    for uid in sorted(allu):
        if "haywire" in uid.lower() or "cyrus" in uid.lower():
            u = allu[uid]
            print("[recon] %-28s kind=%-8s faction=%-18s pool=%s traits=%s"
                  % (uid, u["kind"], fac(u), uid in pl, traits_of(u)))

    # --- 4. porteurs par nom d'ability -------------------------------------------------------
    for name in ("MawClawsOfThyrax", "SabreOfSacrifice", "PurgeResponse", "HaywireMine",
                 "FirstAmongTraitors", "CabalOfSorcerers", "WisdomOfTheAncients",
                 "MastersOfManoeuvre"):
        porteurs = []
        for uid, u in allu.items():
            for voie in ("activeAbilities", "passiveAbilities", "mythicAbilities",
                         "tertiaryAbilities", "relicAbilities"):
                if name in (u.get(voie) or []):
                    porteurs.append((uid, u["kind"], voie, uid in pl))
        # les reliques : table d'items
        print("[recon] %-22s porteurs(voies unite)=%s" % (name, porteurs))

    # --- 5. la table des reliques (items) ----------------------------------------------------
    cfg = gc._cfg()
    print("[recon] cles racine gameconfig : %s" % sorted(cfg.keys()))
    for k in cfg:
        if "item" in k.lower() or "relic" in k.lower():
            blob = cfg[k]
            print("[recon] section %s : type=%s taille=%s" % (k, type(blob).__name__, len(blob)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
