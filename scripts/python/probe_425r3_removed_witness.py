"""#425-r3 -- TEMOIN LIVE : un effet `Removed` reste-t-il dans une liste possedee ?

Pendant live du scan binaire (`probe_425r3_removed_writers.py`). Le decompile etablit que
`IdunBattle.Operations.RemoveEffectOperation$$Execute` -- SEUL ecrivain de
`EffectComponent.Removed` mesure sur le build -- fait `List.Remove` sur
`EffectsOwnedComponent.ActiveEffectIds` de l'entite `OwnerId` AVANT de poser `Removed = 1`,
dans le MEME bloc conditionnel. Corollaire : un id encore present dans une liste possedee
ne peut pas porter `Removed = true`, donc le filtre `if (info && info.removed) continue;`
de `readEffectsByTile` / `readEffectsByUnit` (`frida/hooks/game/effects.ts`) ne peut RIEN
jeter.

CE PROBE MESURE LE COMPORTEMENT PRESENT, il ne re-demontre pas le decompile. Deux
quantites, sur plusieurs tours joues (pour PROVOQUER des retraits : expirations de duree,
morts d'unites -> `KillUnitOperation$$RemoveEffects`) :

  T1  effets PUBLIES portant `removed: true`
      Doit valoir 0. C'est un temoin FAIBLE et il est dit tel quel : le filtre les jette
      en amont de la publication, donc 0 est attendu MEME si l'invariant etait faux.
      Il ne prouve rien seul -- il ne peut que REFUTER (un non-zero contredirait le code).

  T2  entites Effect ORPHELINES = presentes comme entite (`effectAbilityStates`, canal
      SANS filtre d'appartenance) mais dans AUCUNE liste possedee publiee.
      C'est la trace observable du retrait. Un effet retire de sa liste mais dont
      l'ENTITE survit apparait ici. C'est le temoin qui porte l'information.

TRI-ETAT : tout RPC muet rend `None`, jamais 0. Un compte n'est imprime que s'il a ete
MESURE ; sinon la ligne dit `PAS MESURE` et le probe sort en rc 2.

Reproduction :
    python scripts/python/probe_425r3_removed_witness.py --tours 4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))


def _index_effets(rows) -> dict | None:
    """`effectAbilityStates.effects[]` -> {effectId: row}. `None` = PAS MESURE."""
    if rows is None:
        return None
    out = {}
    for e in rows:
        if isinstance(e, dict) and e.get("effectId") is not None:
            out[int(e["effectId"])] = e
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="#425-r3 temoin live des effets Removed")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--tours", type=int, default=4)
    ap.add_argument("--p-units", default="ultraTitus,orksNob")
    ap.add_argument("--a-units", default="tauCrisis,tauShadowsun")
    ap.add_argument("--state-file", default=None)
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, a, t=120):
        try:
            r = _rpc(sid, m, [a], timeout=t)
        except Exception as exc:                     # noqa: BLE001
            print("   RPC %s : PAS MESURE (%s)" % (m, exc))
            return None
        val = (r.get("result") if isinstance(r, dict) and "result" in r else r)
        if isinstance(val, dict) and val.get("ok") is False:
            print("   RPC %s : PAS MESURE (%s)" % (m, val.get("error")))
            return None
        return val or {}

    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    state_file = Path(args.state_file) if args.state_file else (
        logs / "p425r3_witness_state.json")
    state_file.unlink(missing_ok=True)

    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed), "--rank", "17",
           "--board", args.board, "--p-units", args.p_units,
           "--a-units", args.a_units, "--no-ai", "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        sys.stdout.write((p.stdout or "")[-2500:])
        sys.stdout.write((p.stderr or "")[-2500:])
        print("PAS MESURE : build KO (aucun runner monte)")
        return 2
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    sid = _resolve_session()
    print("runner %s (session %s) board=%s seed=%s" % (rid, sid, args.board, args.seed))

    total_removed_publies = 0
    mesures = 0
    rc = 0
    # ANTI-CONFOND (leçon de la 1re passe de cette tranche) : sans lui, le probe a releve
    # QUATRE FOIS le meme instant -- 24 entites / 14 publies / 10 orphelins a l'identique --
    # et l'a rendu comme « stable sur 4 tours ».
    # Le discriminant est la SIGNATURE D'ETAT, pas le numero de tour : mesure ici,
    # `aiturn` clot le tour d'une EQUIPE et `decisionView.turn` reste a 3 pendant que
    # l'etat bouge reellement (24 -> 28 -> 30 entites Effect). Compter par `turn` aurait
    # rejete des releves DISTINCTS ; ne compter par rien aurait accepte des doublons.
    tours_vus: list[int | None] = []
    signatures: set[tuple] = set()
    publies_precedent: dict[int, str] | None = None
    disparus_total: list[tuple[int, str]] = []
    try:
        for passe in range(args.tours + 1):
            print("\n-- passe %d --" % passe)
            eas = rpc(sid, "effectAbilityStates", {"runnerId": rid}, 120)
            idx = _index_effets(eas.get("effects") if isinstance(eas, dict) else None)
            tm = rpc(sid, "tileMeta", {"runnerId": rid, "includeInactive": True}, 90)
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                           "allAbilities": True,
                                           "includeInactive": True}, 150)
            if idx is None or tm is None or dv is None:
                print("   PAS MESURE : un canal est muet -- aucun compte rendu pour ce tour")
                rc = 2
                break

            tiles = tm.get("tiles") if isinstance(tm, dict) else tm
            publies: dict[int, str] = {}
            removed_publies = []
            for t in (tiles or []):
                for e in (t.get("effects") or []):
                    if e.get("effectId") is not None:
                        publies[int(e["effectId"])] = "tuile(%s,%s)" % (t.get("col"), t.get("row"))
                    if e.get("removed") is True:
                        removed_publies.append(("tuile", e.get("effectId"), e.get("name")))
            for u in (dv.get("units") or []) + (dv.get("mows") or []):
                for e in (u.get("effects") or []):
                    if e.get("effectId") is not None:
                        publies[int(e["effectId"])] = "unite(%s)" % u.get("id")
                    if e.get("removed") is True:
                        removed_publies.append(("unite", e.get("effectId"), e.get("name")))

            tour = dv.get("turn") if isinstance(dv, dict) else None
            tours_vus.append(tour)
            signature = (len(idx), tuple(sorted(idx)), tuple(sorted(publies)))
            deja_vu = signature in signatures
            signatures.add(signature)
            orphelins = sorted(set(idx) - set(publies))
            total_removed_publies += len(removed_publies)
            if deja_vu:
                print("   ETAT INCHANGE -- releve NON compte comme mesure distincte")
            else:
                mesures += 1
            print("   tour                               : %s" % tour)
            print("   entites Effect (canal SANS filtre) : %d" % len(idx))
            print("   ids publies (tuiles + unites)      : %d" % len(publies))
            print("   T1 publies avec removed=true       : %d  %s"
                  % (len(removed_publies), removed_publies or ""))
            print("   T2 entites Effect ORPHELINES       : %d" % len(orphelins))
            for oid in orphelins[:12]:
                r = idx[oid]
                print("      id=%-5s type=%-6s name=%-40s active=%s"
                      % (oid, r.get("effectType"), r.get("name"), r.get("active")))

            # T3 -- RETRAITS OBSERVES : un id publie a la passe precedente et absent
            # maintenant a QUITTE une liste possedee. C'est le seul evenement qui puisse
            # exhiber le vice cherche : s'il etait publie avec `removed: true` avant de
            # disparaitre, le filtre aurait masque un effet que le natif comptait encore.
            if publies_precedent is not None:
                partis = sorted(set(publies_precedent) - set(publies))
                if partis:
                    print("   T3 ids ayant QUITTE une liste possedee : %d" % len(partis))
                    for pid in partis[:12]:
                        encore = "entite VIVANTE" if pid in idx else "entite DETRUITE"
                        print("      id=%-5s %-16s (etait %s)"
                              % (pid, encore, publies_precedent[pid]))
                        disparus_total.append((pid, encore))
            publies_precedent = publies

            if passe < args.tours:
                # Voie CLI (`runner.md`) -- il n'existe PAS de RPC `aiTurn`. La 1re passe de
                # cette tranche appelait un nom inexistant, dont l'echec passait pour un
                # succes : le tour n'avancait pas et le probe rendait 4 releves identiques.
                r = subprocess.run(
                    [sys.executable, "rl_duel.py", "aiturn", "--state-file", str(state_file)],
                    cwd=str(PYDIR), capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
                if r.returncode != 0:
                    print("   avance de tour KO (rc=%s) : %s"
                          % (r.returncode, (r.stderr or r.stdout or "")[-400:]))
                    break
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=60)
            print("\nrunner %s dispose" % rid)
        except Exception as exc:                     # noqa: BLE001
            print("\nATTENTION : dispose du runner %s en echec (%s)" % (rid, exc))

    print("\n=== BILAN ===")
    print("etats DISTINCTS mesures : %d  (numeros de tour releves : %s)"
          % (mesures, tours_vus))
    if mesures == 0:
        print("PAS MESURE : aucun releve n'a abouti")
        return 2
    if mesures < 2:
        print("ATTENTION : un seul etat distinct -- ce releve ne dit RIEN d'une")
        print("            transition, et donc rien d'un RETRAIT d'effet.")
        rc = rc or 1
    print("T1 total d'effets PUBLIES avec removed=true : %d" % total_removed_publies)
    print("    (0 attendu -- temoin FAIBLE : le filtre les jette avant publication,")
    print("     donc 0 est attendu meme si l'invariant etait faux ; il ne peut que REFUTER)")
    print("T3 retraits OBSERVES (ids sortis d'une liste possedee) : %d" % len(disparus_total))
    if not disparus_total:
        print("    Aucun retrait n'a eu lieu sur ce regime : le temoin n'a donc PAS")
        print("    exerce le chemin `RemoveEffectOperation`. NON CONCLUANT sur ce point")
        print("    -- ce n'est pas une confirmation, c'est une absence de regime.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
