#!/usr/bin/env python3
"""ATELIER FRIDA -- garde de VIVACITE des deux expositions ajoutees au decodeur (#N11, #R34).

Ce probe ne mesure pas une mecanique de jeu : il verifie que deux CANAUX que le hook vient
d'ouvrir portent reellement une valeur, et -- pour celui qui le permet -- qu'ils en portent
PLUS D'UNE. C'est la parade a la classe de defaut dominante de la campagne : un champ cable
mais toujours egal a sa valeur par defaut est INDISCERNABLE d'un champ mort, et aucun test
d'egalite live/offline ne peut faire la difference.

  A. `combatSnapshot.units[].turnsFinished` (#N11) -- mirror de
     `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(unit) -> Int32`, le compteur PER-UNITE
     que lit `OwnerHasFinishedMinTurns`. On l'INVOQUE au lieu de lire le champ a `+0x5c` : un
     offset brut est vrai jusqu'a la prochaine MAJ du jeu et faux SILENCIEUSEMENT apres.
     Critere FORT : au moins DEUX valeurs distinctes coexistent dans le meme snapshot. Une
     unite apparue en cours de bataille (summon) a un compteur inferieur aux unites presentes
     au deploiement -- c'est ce qui prouve que le compteur est PER-UNITE et non global, et
     c'est exactement l'ecart que `load_state` ecrasait en mettant tout le monde a 0.

  B. `aiPlaybookPredict.events[].preventOverkill` (#R34) -- `DamagePredictionResult.PreventOverkill`
     @struct+0xB3, soit event+0xBB (l'event embarque `AttackHitPrediction` a +0x08). C'est le
     5e argument de la surcharge privee 8-args d'`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`,
     que le port passe a `0` EN DUR faute d'exposition. Critere FAIBLE assume : on verifie que la
     cle DESCEND et qu'elle est booleenne-compatible. La faire varier exige un porteur de
     `FuelledByFury_BlockOverkillEffect` (flag 0x13) en cible -- montage separe, hors de ce probe.

Sortie ASCII pure (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parent.parent.parent


def rpc(sid: int, method: str, args: dict, timeout_ms: int = 60000):
    body = json.dumps({"method": method, "args": [args], "timeout": timeout_ms}).encode()
    req = urllib.request.Request(f"{HOST}/api/scripts/{sid}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_ms / 1000 + 30) as r:
        return json.loads(r.read()).get("result")


def live_session() -> int:
    with urllib.request.urlopen(f"{HOST}/api/admin/status", timeout=15) as r:
        st = json.loads(r.read())
    s = st.get("session")
    if not s or s.get("status") != "running":
        sys.exit("[error] aucune session Frida vivante -- injecter puis amorce")
    return int(s["id"])


def part_turns_finished(sid: int, rid: int) -> bool:
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid})
    units = (snap or {}).get("units") or []
    if not units:
        print("[A] ECHEC : combatSnapshot ne rend aucune unite")
        return False
    vals = {}
    for u in units:
        vals.setdefault(u.get("turnsFinished"), []).append(u.get("entityId"))
    if None in vals:
        print("[A] ECHEC : turnsFinished vaut None (methode native non resolue) sur %d unite(s)"
              % len(vals[None]))
        return False
    print("[A] turnsFinished, distribution : " + "  ".join(
        "tf=%s -> %d unite(s) %s" % (k, len(v), v[:8]) for k, v in sorted(vals.items())))
    if len(vals) < 2:
        print("[A] canal LU mais NON DISCRIMINE : une seule valeur (%s) dans ce snapshot."
              % list(vals)[0])
        print("    Jouer des tours jusqu'a l'apparition d'un summon, ou charger un etat"
              " mi-bataille : sans DEUX valeurs, ce canal ne se distingue pas d'un canal mort.")
        return False
    print("[A] OK : %d valeurs distinctes -- le compteur est PER-UNITE, pas global." % len(vals))
    return True


def part_prevent_overkill(sid: int, rid: int) -> bool:
    dv = rpc(sid, "decisionView", {"runnerId": rid})
    units = [u for u in ((dv or {}).get("units") or []) if not u.get("isDead")]
    teams = {u.get("team") for u in units}
    if len(teams) < 2:
        print("[B] ECHEC : une seule equipe vivante, pas de couple attaquant/cible")
        return False
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid})
    by_id = {u.get("entityId"): u for u in ((snap or {}).get("units") or [])}
    tried = []
    for att in units:
        # `combatSnapshot.normalAttack` est un RESUME de degat (minDmg/maxDmg/hits/vsTarget) et ne
        # porte AUCUN id d'ability -- l'attaque normale est un `ActiveAbilityType` CONCRET par
        # unite, pas un 17 generique. Les ids exploitables sont dans `abilityStates`, qui est le
        # capteur des actives reellement portees par l'unite a son niveau.
        st = (by_id.get(att.get("id")) or {}).get("abilityStates") or []
        if isinstance(st, dict):
            st = [st]
        cands = [s.get("id") for s in st if s.get("id") and s.get("kind") == "active"]
        for ab in cands:
            for tgt in units:
                if tgt.get("team") == att.get("team"):
                    continue
                ev = rpc(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": att.get("id"),
                                                    "targetId": tgt.get("id"), "abilityType": ab})
                tried.append((att.get("id"), tgt.get("id"), ab, (ev or {}).get("ok"),
                              len((ev or {}).get("events") or [])))
                for e in ((ev or {}).get("events") or []):
                    if "preventOverkill" not in e:
                        print("[B] ECHEC : la cle preventOverkill est ABSENTE de l'event decode."
                              " Cles vues : %s" % sorted(e))
                        return False
                    print("[B] OK : preventOverkill DESCEND -- att=%s tgt=%s ability=%s valeur=%r"
                          % (att.get("id"), tgt.get("id"), ab, e["preventOverkill"]))
                    print("    (voisins de controle : mightCrit=%r forceOverkill=%r"
                          " limitedByMinHp=%r)" % (e.get("mightCrit"), e.get("forceOverkill"),
                                                   e.get("limitedByMinHp")))
                    return True
    print("[B] INDETERMINE : aucun couple n'a produit d'event de degat. Essais = %s" % tried[:6])
    print("    Ce n'est PAS une preuve que la cle manque -- c'est un montage sans prediction.")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state-file", default=str(ROOT / "logs" / "_atelier_frida.json"))
    ap.add_argument("--part", choices=("all", "turns", "overkill"), default="all")
    a = ap.parse_args()

    sid = live_session()
    rid = json.loads(Path(a.state_file).read_text())["runnerId"]
    print("session=%d runner=%d" % (sid, rid))

    ok = True
    if a.part in ("all", "turns"):
        ok &= part_turns_finished(sid, rid)
    if a.part in ("all", "overkill"):
        ok &= part_prevent_overkill(sid, rid)
    print("VERDICT : " + ("OK" if ok else "INCOMPLET"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
