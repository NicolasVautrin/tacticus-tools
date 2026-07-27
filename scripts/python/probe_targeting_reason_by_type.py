"""Probe de CONTROLE de METHODE -- `abilityReason` resout-il l'ability par TYPE, ou par
l'instance portee par le caster ?

Enjeu : `necroPlasmancer` (porteur de HarbingerOfDestruction 1008) est dans
`UNSPAWNABLE_FALLBACK` -- il throw au spawn, donc il n'entre dans AUCUN runner. Si
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason(attacker, tile, defender,
abilityType)` resout l'`AActiveAbility` par le TYPE (registre global) et non par les actives de
l'attaquant, alors le verdict natif d'un `abilityType` donne ne depend pas du porteur, et 1008 est
confrontable depuis n'importe quel caster.

METHODE (discriminante, pas une croyance) : on interroge le MEME `abilityType` (1202
VigilanceEternal) depuis son VRAI porteur (custoKyrus) et depuis un caster qui ne l'a PAS
(necroOverlord), sur les MEMES cibles, apres avoir mis les deux casters a la MEME distance de la
cible (sinon `TargetIsInRange` masque la comparaison). Verdicts identiques => resolution par TYPE.

Usage : python probe_targeting_reason_by_type.py [--board MC1_67] [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    args = ap.parse_args()
    sid = R._resolve_session()
    with tempfile.TemporaryDirectory(prefix="reasontype_") as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        p = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--seed", args.seed, "--board", args.board,
             "--p-units", "custoKyrus,necroOverlord", "--a-units", "eldarRanger,astraBullgryn",
             "--no-ai", "--state-file", str(state_file)],
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not state_file.exists():
            print("BUILD KO:", (p.stderr or p.stdout or "")[-400:])
            return 1
        rid = json.loads(state_file.read_text())["runnerId"]

        def rpc(m, b, t=90):
            return _unwrap(R._rpc(sid, m, [b], timeout=t))

        try:
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            units = [u for u in (dec.get("units") or []) if u.get("alive")]
            by_vis = {u.get("visualId"): u for u in units}
            owner_v = by_vis.get("custoKyrus")
            other_v = by_vis.get("necroOverlord")
            if owner_v is None or other_v is None:
                print("casters absents:", sorted(by_vis))
                return 1
            # Meme distance a la cible pour les deux casters : on POSE le porteur reel a la
            # place de l'autre. `applyAction move` echouerait (tuile occupee) -> on compare
            # plutot les regles INSENSIBLES a la position (TargetIsEnemy sur un ALLIE), ce qui
            # suffit a trancher « par type » vs « par instance ».
            print("caster_owner=u%d (custoKyrus)  caster_other=u%d (necroOverlord)"
                  % (owner_v["id"], other_v["id"]))
            print("abil  caster            target            hex           reasons")
            same = True
            for ab in (1202, 1008, 1226, 1207):
                rows = {}
                for cv in (owner_v, other_v):
                    for tv in units:
                        if tv["id"] == cv["id"]:
                            continue
                        nat = rpc("abilityReason", {"runnerId": rid, "casterId": cv["id"],
                                                    "abilityType": ab, "targetId": tv["id"]}, 60)
                        tr = (nat or {}).get("targetReason") or {}
                        rows.setdefault(tv["visualId"], {})[cv["visualId"]] = (
                            tr.get("hex"), ",".join(tr.get("reasons") or []) or "-")
                        print("%-5d %-17s %-17s %-13s %s"
                              % (ab, cv["visualId"], tv["visualId"], tr.get("hex"),
                                 ",".join(tr.get("reasons") or []) or "-"))
                # compare, pour les cibles vues par les DEUX casters, sur les regles non
                # positionnelles (on ignore TargetIsInRange 0x8000000, sensible a la distance)
                for tgt, byc in rows.items():
                    vals = []
                    for cvis, (hx, names) in byc.items():
                        v = int(hx, 16) if hx else 0
                        vals.append(v & ~0x8000000)
                    if len(set(vals)) > 1:
                        same = False
                        print("  DIVERGE sur %s pour ability %d : %s" % (tgt, ab, byc))
            print("\nVERDICT: resolution %s"
                  % ("par TYPE (verdicts identiques hors portee)" if same
                     else "DEPENDANTE du porteur -- 1008 NON confrontable par proxy"))
            return 0 if same else 2
        finally:
            try:
                R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
