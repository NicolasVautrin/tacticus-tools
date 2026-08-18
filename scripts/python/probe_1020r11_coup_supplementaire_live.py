"""#1020-r11 -- D'OU VIENT LE COUP SUPPLEMENTAIRE quand le protecteur est ADJACENT ?

Sonde de DECOMPOSITION, pas de verdict. Elle rejoue le montage nomme de #1020-r6
(`probe_1020_savior_protocols_live.stage()`, attaquant `orksRuntherd`) et DUMPE, en clair :

  * le FLUX NATIF ORDONNE (chaque pas : `step`, tags), qui est le seul canal ou l'on peut
    voir a quelle SOUS-OPERATION appartient chaque coup -- un total ne le dit pas ;
  * la decomposition du PORT par SERIE (`_run_hits` instrumentee) : `hits` demandes,
    `hit_index0`, coups executes, tirages.

Les deux bras (drone ADJACENT / drone LOIN) sont joues sur la MEME seed et le MEME board,
et le dump porte les deux -- c'est la seule difference du montage, donc la seule cause
possible de l'ecart.

ASCII only. Usage :
  python probe_1020r11_coup_supplementaire_live.py [--seed 777] [--board MC1_67] [--dmg 900]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
REPO = ROOT.parents[1]

from probe_1020_savior_protocols_live import (          # noqa: E402
    MontageError, _hp, _r, _sid, stage)
from probe_1020r6_groupes_source_ability_live import (  # noqa: E402
    ATTAQUANT, _ids, _normal_attack_id)
from engine.entities.pathfinding.board import Board     # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402


def _flux_ordonne(res: dict) -> list:
    """Le flux natif A PLAT, DANS L'ORDRE : un enregistrement par noeud portant un `step`.

    Les tags sont des CHAINES JSON cote RPC (`"tags": "{...}"`) -- les lire comme un dict
    rendrait un flux vide."""
    out = []

    def tags_of(node):
        t = node.get("tags")
        if isinstance(t, str):
            try:
                return json.loads(t)
            except ValueError:
                return {}
        return t if isinstance(t, dict) else {}

    def walk(node, chemin):
        if isinstance(node, dict):
            if "step" in node:
                out.append({"step": node.get("step"), "chemin": chemin,
                            "tags": tags_of(node)})
            for k, v in node.items():
                walk(v, chemin + "/" + str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, chemin + "[%d]" % i)

    walk(res, "")
    return out


def mesure(sid, rid, ids, ab_id):
    hp0, ob0 = _hp(sid, rid)
    dv0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    snap0 = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
    rng0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    res = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ids["att"], "targetId": ids["victime"],
        "abilityType": int(ab_id)}}, 120)
    rng1 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    return {"hp0": hp0, "dv0": dv0, "ob0": ob0, "snap0": snap0, "rng0": rng0, "rng1": rng1,
            "res": res,
            "ok": bool(res.get("ok")) and all(a.get("ok") for a in (res.get("actions") or []))}


def rejoue_port(nat, ids, board) -> dict:
    """Rejoue l'attaque cote PORT sur le MEME etat et le MEME MT, en instrumentant les DEUX
    etages qui decident du NOMBRE de coups : `_run_hits` (une SERIE) et
    `execute_additional_hits` (les GROUPES)."""
    from engine.runner.snapshot import load_state
    from engine.runner.operations.damage import AttackDamageOperation
    import engine.runner.operations.additional_hits as AH
    import engine.runner.operations.damage_ops.normal as NRM
    import engine.runner.operations.damage_ops.ability as ABL

    st = load_state(nat["dv0"], nat["ob0"], nat["snap0"], board=board)
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(nat["rng0"]["mt"]), nat["rng0"]["mti"]
    st.rng = rng

    series = []
    vrai_rh = AttackDamageOperation._run_hits.__func__ \
        if hasattr(AttackDamageOperation._run_hits, "__func__") else AttackDamageOperation._run_hits

    def trace_rh(*a, **kw):
        # signature positionnelle : (rng, hit_nc, hit_cr, crit_chance, crit_enabled, hits, ...)
        hits = a[5] if len(a) > 5 else kw.get("hits")
        r = vrai_rh(*a, **kw)
        series.append({"hits_demandes": hits, "hit_index0": kw.get("hit_index0", 0),
                       "bonus_hit_chance": kw.get("bonus_hit_chance"),
                       "hits_executes": r.get("hits_executed"),
                       "bonus_hits": r.get("bonus_hits"),
                       "per_hit": list(r.get("per_hit") or []),
                       "rolls": list(r.get("rolls") or []),
                       "crits": list(r.get("crits") or []),
                       "next_hit_index": r.get("next_hit_index"),
                       "mti_apres": st.rng.mti})
        return r

    groupes = []
    vrai_ah = AH.execute_additional_hits
    o_n, o_a = NRM.execute_additional_hits, ABL.execute_additional_hits

    def trace_ah(state, attacker_id, target_id, tgt, thc, groups, mods, def_mods, armor,
                 hit_mult, block_sources, shc, spread_pct=None, extra_pierce=0,
                 bonus_hit_chance=None, hit_index0=0, crit_allowed0=True, attack_profile=None,
                 hit_interceptor=None, failed_block0=None, damaging_done0=False,
                 source_ability=None):
        """SIGNATURE PLEINE, jamais `*args/**kwargs` : le cliquet #393
        (`test_additional_hits_variant_signatures_offline.py`) l'exige, et pour une raison qui
        vaut ici comme ailleurs -- un fourre-tout resterait vert en cessant d'exercer l'etage."""
        groupes.append([{k: g.get(k) for k in ("count", "profile", "min", "max", "amount",
                                               "source")} for g in (groups or [])])
        return vrai_ah(state, attacker_id, target_id, tgt, thc, groups, mods, def_mods, armor,
                       hit_mult, block_sources, shc, spread_pct=spread_pct,
                       extra_pierce=extra_pierce, bonus_hit_chance=bonus_hit_chance,
                       hit_index0=hit_index0, crit_allowed0=crit_allowed0,
                       attack_profile=attack_profile, hit_interceptor=hit_interceptor,
                       failed_block0=failed_block0, damaging_done0=damaging_done0,
                       source_ability=source_ability)

    AttackDamageOperation._run_hits = staticmethod(trace_rh)
    AH.execute_additional_hits = trace_ah
    NRM.execute_additional_hits = trace_ah
    ABL.execute_additional_hits = trace_ah
    try:
        r = AttackDamageOperation.execute(st, int(ids["att"]), int(ids["victime"]))
    finally:
        AttackDamageOperation._run_hits = staticmethod(vrai_rh)
        AH.execute_additional_hits = vrai_ah
        NRM.execute_additional_hits = o_n
        ABL.execute_additional_hits = o_a
    ah = (r or {}).get("additional_hits") or {}
    return {"series": series, "groupes": groupes, "mti": st.rng.mti,
            "arme_per_hit": (r or {}).get("per_hit"),
            "groupe_per_hit": ah.get("per_hit"),
            "groupe_hits": ah.get("hits")}


def bras(seed: int, board_id: str, dmg, loin: bool) -> dict:
    sid = _sid()
    rid, sf = stage(seed, board_id, attaquant=ATTAQUANT, dmg_attaquant=dmg, drone_loin=loin)
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        ids, _dv = _ids(sid, rid)
        if not all(k in ids for k in ("att", "victime", "drone")):
            raise MontageError("entites introuvables : %s" % ids)
        ab_id = _normal_attack_id(sid, rid, ids["att"])
        nat = mesure(sid, rid, ids, ab_id)
        if not nat["ok"]:
            raise MontageError("applyAction REFUSEE : %s" % json.dumps(nat["res"])[:400])
        port = rejoue_port(nat, ids, board)
        return {"ids": ids, "ability": ab_id,
                "mti_natif": (nat["rng1"] or {}).get("mti"),
                "mti0": (nat["rng0"] or {}).get("mti"),
                "flux": _flux_ordonne(nat["res"]),
                "port": port}
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        Path(sf).unlink(missing_ok=True)


def run(seed: int, board_id: str, dmg, sortie: Path) -> int:
    out = {"seed": seed, "board": board_id, "dmg": dmg}
    for nom, loin in (("adjacent", False), ("loin", True)):
        out[nom] = bras(seed, board_id, dmg, loin)
        b = out[nom]
        print("== bras %s : ids=%s ability=%s mti %s -> %s"
              % (nom, b["ids"], b["ability"], b["mti0"], b["mti_natif"]))
        print("   PORT arme=%s groupe=%s (groupe hits=%s)"
              % (b["port"]["arme_per_hit"], b["port"]["groupe_per_hit"],
                 b["port"]["groupe_hits"]))
        for i, s in enumerate(b["port"]["series"]):
            print("   PORT serie %d : demandes=%s idx0=%s bonus_chance=%s executes=%s "
                  "bonus=%s per_hit=%s next_idx=%s"
                  % (i, s["hits_demandes"], s["hit_index0"], s["bonus_hit_chance"],
                     s["hits_executes"], s["bonus_hits"], s["per_hit"], s["next_hit_index"]))
        print("   PORT groupes=%s" % b["port"]["groupes"])
        pas = [(p["step"], sorted(p["tags"].keys())) for p in b["flux"]]
        print("   NATIF pas distincts=%s" % sorted({p[0] for p in pas}))
        print("   NATIF nb pas=%d" % len(pas))
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("DUMP: %s" % sortie)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--dmg", type=int, default=900)
    ap.add_argument("--dump", default=str(REPO / "logs" / "probe_1020r11_flux.json"))
    a = ap.parse_args()
    return run(a.seed, a.board, a.dmg, Path(a.dump))


if __name__ == "__main__":
    raise SystemExit(main())
