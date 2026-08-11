"""#930 -- confront LIVE de la face COMBAT du passif `KustomForceFieldReworked` (`orksBigMek`).

Ce que ce probe MESURE, et qu'aucune table ne donne :

  * QUI porte les deux effets-entites (`decisionView.effects` du Big Mek) ;
  * QUI recoit la `ValueModification` de `FixedArmor`, et DE QUELLE SOURCE
    (`statModSources` : la cle est l'ENTITE-EFFET, donc les deux effets sont separables) ;
  * COMBIEN exactement -- le discriminant du swap de variable (`extraArmor` vs `extraArmor_2`) ;
  * la RE-EVALUATION au mouvement, dans les DEUX sens (entree dans le ring, sortie du ring).

Le montage est DISCRIMINANT par construction : quatre allies couvrant les quatre cases du couple
(faction Ork ?) x (adjacent ?), plus un ennemi qu'on peut amener au contact pour exercer le volet
`Friends` du selecteur.

    python probe_930_kustom_force_field_reworked.py --seed 777 --board MC1_67
    python probe_930_kustom_force_field_reworked.py --offline-only      # aucun runner

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
# SORTIES -> `logs/` (gitignore, meurt avec le worktree) : `data/` est VERSIONNE (#349).
LOGS = PYDIR.parent.parent / "logs" / "runners"

CARRIER = "orksBigMek"          # HERO, au pool rank 17 (`rl_duel build --list-pool`)
ALLY_ORK = "orksNob"            # ami ORK      -> effet 1567 (`extraArmor_2`)
ALLY_OTHER = "ultraApothecary"  # ami NON-Ork  -> effet 1566 (`extraArmor`)
ALLY_FAR = "astraBullgryn"      # ami NON-Ork, place HORS du ring au depart
FOE = "necroWarden"

ABILITY = "KustomForceFieldReworked"          # TriggeredAbilityType 0x60b = 1547
EFFECT_NON_ORKS = "KustomForceFieldReworked"       # EffectType 0x61e = 1566
EFFECT_ORKS = "KustomForceFieldReworked_Orks"      # EffectType 0x61f = 1567
FIXED_ARMOR = 16                              # StatType.FixedArmor -- `statType` du helper natif


def _unwrap(r):
    return r["result"] if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=90):
    from rl_collect_batch import _rpc
    return _unwrap(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def build(state_file: str, seed: str, board: str) -> int:
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
                        "--p-units", f"{CARRIER},{ALLY_ORK},{ALLY_OTHER},{ALLY_FAR}",
                        "--a-units", FOE, "--state-file", state_file],
                       cwd=str(PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stdout[-3000:]); print(p.stderr[-3000:])
        raise SystemExit("build KO")
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def fixed_armor_by_unit(sid, rid) -> dict:
    """{entityId: (total, [(sourceEffectId, amount), ...])} pour `FixedArmor`."""
    sm = rpc(sid, "statModSources", {"runnerId": rid, "statType": FIXED_ARMOR}, 90)
    out = {}
    for u in sm.get("units") or []:
        fa = (u.get("mods") or {}).get("fixedArmor")
        if fa is None:
            out[int(u["entityId"])] = (0, [])
        else:
            out[int(u["entityId"])] = (int(fa.get("total") or 0),
                                       [(int(s.get("source")), int(s.get("amount")))
                                        for s in fa.get("bySource") or []])
    return out


def offline_expected(level: int, mult: int) -> dict:
    """Ce que le PORT rend pour les deux effets, au meme niveau/multiplier."""
    sys.path.insert(0, str(PYDIR))
    from engine.entities.effects.factory import EFFECT_CLASSES
    out = {}
    for nom in (EFFECT_NON_ORKS, EFFECT_ORKS):
        e = EFFECT_CLASSES[nom](name=nom)
        e.ability_level = level
        e.ability_variables_multiplier = mult
        out[nom] = e.aura_stat_modification_amount()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--level", type=int, default=50)
    ap.add_argument("--mult", type=int, default=180)
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()

    exp = offline_expected(a.level, a.mult)
    print("[offline] port, level=%d mult=%d :" % (a.level, a.mult))
    for k, v in exp.items():
        print("   %-32s -> %s" % (k, v))
    if a.offline_only:
        return

    from rl_collect_batch import _resolve_session
    sid = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    sf = a.state_file or str(LOGS / "_930_kff.json")
    rid = build(sf, a.seed, a.board)
    try:
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ids, pos = {}, {}
        for u in dv.get("units") or []:
            if u.get("alive"):
                ids[u.get("visualId")] = u["id"]
                p = u.get("pos") or {}
                pos[u["id"]] = (p.get("col"), p.get("row"))
        print("[live] unites :", json.dumps({k: (v, pos.get(v)) for k, v in ids.items()}))
        effs = {u["id"]: [e.get("name") for e in (u.get("effects") or [])]
                for u in (dv.get("units") or []) if u.get("alive")}
        print("[live] effets du porteur u%s : %s" % (ids.get(CARRIER), effs.get(ids.get(CARRIER))))

        def dump(label):
            fa = fixed_armor_by_unit(sid, rid)
            print("[%s]" % label)
            for vid, uid in sorted(ids.items()):
                t, by = fa.get(uid, (0, []))
                print("   u%-4s %-18s pos=%-8s total=%-6s bySource=%s"
                      % (uid, vid, pos.get(uid), t, by))
            return fa

        def move(uid, col, row):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 40)
            pos[uid] = (col, row)

        dump("seed")
        # deux mouvements SYMETRIQUES : un allie ENTRE dans le ring, un autre en SORT.
        bm = pos[ids[CARRIER]]
        move(ids[ALLY_FAR], int(bm[0]) + 1, int(bm[1]))
        dump("far_in")
        move(ids[ALLY_OTHER], int(bm[0]), int(bm[1]) + 3)
        dump("other_out")
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        print("[dispose] runner", rid)


if __name__ == "__main__":
    main()
