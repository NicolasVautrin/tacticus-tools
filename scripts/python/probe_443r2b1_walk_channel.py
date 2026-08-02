"""#443-r2-b1 -- la bascule du canal deplace-t-elle une DECISION, sur une marche d'agreement ?

Le balayage par paire (`probe_443r2b1_pair_sweep.py`) mesure des UTILITES. Ici on mesure ce qui
compte pour l'agreement : l'ACTION CHOISIE. Une utilite qui bouge de +35 ne deplace la decision que
si elle change l'argmax -- et inversement, une utilite qui ne bouge nulle part ne peut rien casser.

METHODE -- UNE seule marche, DEUX decisions par pas
--------------------------------------------------
`engine_validate.run_agreement` marche la trajectoire NATIVE et compare, a chaque pas, l'action du
port a celle du natif. Sa sonde par-etage est appelee AVANT `applyAction`, donc sur l'etat EXACT de
la decision : on y rejoue `engine_decide` sur le canal NU (celui d'avant #443-r2-b1) et on confronte
les deux actions du port.

  * le walk lui-meme utilise le canal de PRODUCTION (`decision_view_seed_body`, depuis #443-r2-b1) ;
  * la sonde recapture le canal NU et redecide ;
  * DIFF = la bascule a deplace CETTE decision. Le natif ARBITRE : gain si la decision de production
    matche le natif la ou le canal nu ne matchait pas, regression si l'inverse.

Comparer deux runners (avant / apres) serait FAUX : la marche MUTE l'etat, deux runners divergent des
le premier desaccord. Un seul runner, deux decisions sur le MEME etat, est la seule comparaison
propre.

ANTI-MUET : le rayon de souffle du canal est mesure a CHAQUE pas. Si le canal n'ajoute rien de toute
la marche, la marche ne prouve rien et le probe le DIT (rc != 0).

Usage :
    python probe_443r2b1_walk_channel.py --state-file <ABSOLU> [--board B] [--seed S] [--steps N]
                                         [--p-units ...] [--a-units ...]

rc = nombre de decisions deplacees en REGRESSION (+ 1 si la marche est muette). ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import engine_validate as EV                                     # noqa: E402
import probe_443r2_only_active_overwatch as P501                 # noqa: E402
from engine import weights as W                                  # noqa: E402

P_UNITS = "emperNoiseMarine,ultraEliminatorSgt,bloodDeathCompany"
A_UNITS = "eldarRanger,tauCrisis,orksWarboss"


class MontageError(RuntimeError):
    pass


def _build(state_file: str, board: str, seed: str, p_units: str, a_units: str) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file,
            "--board", board, "--p-units", p_units, "--a-units", a_units]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def ajouts_par_unite(rpc, rid: int) -> dict:
    """`{unitId: [(effectType, nom), ...]}` que le canal `includeInactive` AJOUTE sur cet etat.

    `P501.blast_radius` agrege par TYPE ; ici on garde le porteur, parce que c'est lui qui permet
    d'ATTRIBUER un deplacement de decision (« la cible 84 gagne un 1009 inerte, la 86 rien »)
    au lieu de le constater."""
    d0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    d1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32,
                              "includeInactive": True}, 180)

    def idx(d):
        out = {}
        for u in (d.get("units") or []) + (d.get("mows") or []):
            uid = u.get("id") if u.get("id") is not None else u.get("casterId")
            out[uid] = [(int(e.get("effectType") or -1), e.get("name"))
                        for e in (u.get("effects") or []) if e.get("active") is not False]
            out.setdefault(("all", uid), None)
        return out

    i0 = idx(d0)
    plein = {}
    for u in (d1.get("units") or []) + (d1.get("mows") or []):
        uid = u.get("id") if u.get("id") is not None else u.get("casterId")
        plein[uid] = [(int(e.get("effectType") or -1), e.get("name"))
                      for e in (u.get("effects") or [])]
    return {uid: [x for x in effs if x not in (i0.get(uid) or [])]
            for uid, effs in plein.items()
            if [x for x in effs if x not in (i0.get(uid) or [])]}


def _decompose(rpc, rid, uid, mov_by_unit, predictor, dv_prod, dv_nu, eng, eng_nu) -> list:
    """DECOMPOSITION PAR ETAGE d'une decision deplacee -- on ne CONSTATE pas un argmax qui bascule,
    on dit QUEL etage a bouge.

    Deux etages seulement sont necessaires ici, et ils partitionnent l'utilite de paire du natif :
    la feuille des ABILITIES DECLENCHEES (`engine.utilities.tile.triggered_abilities_attack_utility`,
    ou vivent tous les termes `HasEffect`-gated -- `SUPPRESSIVEFIRE_TargetWithOverwatch`,
    `WireweaveNet_FirstAttack`, ...) et le RESTE (prediction de degat). Si le deplacement est
    integralement dans la feuille, c'est un terme d'effet ; sinon c'est le degat."""
    from engine.ai import context as _ai_ctx
    from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
    out = []
    ab = eng.get("ability") or eng_nu.get("ability")
    tile = eng.get("to") or eng_nu.get("to")
    cibles = {c for c in (eng.get("target"), eng_nu.get("target")) if c is not None}
    if ab is None or tile is None or not cibles:
        return out
    for nom, dv in (("nu", dv_nu), ("production", dv_prod)):
        ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, uid, W.load(), predictor)
        for tgt in sorted(cibles):
            cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
            out.append({"canal": nom, "tgt": tgt,
                        "u": None if cand is None else float(cand["u"]),
                        "feuille_triggered": P501.leaf_term(ctx, uid, ab, tgt, tile)})
    return out


def _norme(a: dict | None) -> tuple:
    """L'action du port, reduite a ce qui est COMPARABLE (kind + destination + ability/cible)."""
    if a is None:
        return ("none",)
    return (a.get("kind"), a.get("to"), a.get("ability"), a.get("target"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="41504")
    ap.add_argument("--p-units", default=P_UNITS)
    ap.add_argument("--a-units", default=A_UNITS)
    ap.add_argument("--steps", type=int, default=14)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    wt = W.load()
    rid = _build(args.state_file, args.board, args.seed, args.p_units, args.a_units)
    rows: list[dict] = []
    ajouts = 0

    def sonde(step, uid, dv, mov_by_unit, nat, eng, predictor):
        nonlocal ajouts
        br = P501.blast_radius(rpc, rid)
        n = br["entrees_include"] - br["entrees_defaut"]
        ajouts += n
        dv_nu = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        eng_nu = EV.engine_decide(sid, rid, dv_nu, mov_by_unit, uid, wt, predictor)
        row = {"step": step, "uid": uid, "ajouts": n, "types": sorted(br["par_type"]),
               "par_unite": ajouts_par_unite(rpc, rid),
               "prod": _norme(eng), "nu": _norme(eng_nu), "etages": None,
               "nat": (nat.get("move") or {}).get("to"),
               "nat_ab": (nat.get("ability") or {}).get("ability"),
               "nat_tgt": (nat.get("ability") or {}).get("target")}
        if _norme(eng) != _norme(eng_nu):
            row["etages"] = _decompose(rpc, rid, uid, mov_by_unit, predictor, dv, dv_nu, eng, eng_nu)
        rows.append(row)

    try:
        print("runner %d | board %s seed %s | steps %d" % (rid, args.board, args.seed, args.steps))
        res = EV.run_agreement(sid, rid, args.steps, wt, log=lambda *_a, **_k: None, probe=sonde)
    finally:
        if not args.keep:
            rpc("disposeRunner", {"runnerId": rid}, 30)

    bouge = [r for r in rows if r["prod"] != r["nu"]]
    pas_vus = [r for r in rows if r["ajouts"] == 0]
    print("\n  pas de decision confrontes : %d  |  ou le canal AJOUTE des inertes : %d"
          % (len(rows), len(rows) - len(pas_vus)))
    if rows:
        t = sorted({x for r in rows for x in r["types"]})
        print("  effectTypes ajoutes par le canal sur la marche : %s" % (t or "AUCUN"))
    # ARBITRAGE PAR LE NATIF -- une decision qui bouge n'est ni bonne ni mauvaise en soi : ce qui la
    # qualifie est le sens du mouvement PAR RAPPORT A L'ORACLE. Meme criteres qu'`engine_validate`
    # (destination du move, couple (ability, cible) du cast), appliques aux DEUX canaux.
    def _matche(a: tuple, r: dict) -> bool:
        kind, to, ab, tgt = a
        if r["nat_ab"] is not None:
            return kind == "ability" and ab == r["nat_ab"] and tgt == r["nat_tgt"]
        return to == r["nat"]

    gain = [r for r in bouge if _matche(r["prod"], r) and not _matche(r["nu"], r)]
    reg = [r for r in bouge if _matche(r["nu"], r) and not _matche(r["prod"], r)]
    autre = [r for r in bouge if r not in gain and r not in reg]
    print("  decisions DEPLACEES par la bascule : %d  (GAIN=%d REGRESSION=%d indifferent=%d)"
          % (len(bouge), len(gain), len(reg), len(autre)))
    for titre, lot in (("GAIN", gain), ("REGRESSION", reg), ("INDIFFERENT", autre)):
        for r in lot:
            print("     [%-11s] step %-2d u%-3d  nu=%s  production=%s  | natif move=%s ab=%s tgt=%s"
                  % (titre, r["step"], r["uid"], r["nu"], r["prod"], r["nat"], r["nat_ab"],
                     r["nat_tgt"]))
            # ATTRIBUTION : ce que le canal ajoute sur CHAQUE entite en jeu dans ce deplacement.
            for e in (r["uid"], r["nu"][3], r["prod"][3], r["nat_tgt"]):
                if e is None:
                    continue
                print("        u%-3d recoit du canal : %s"
                      % (e, r["par_unite"].get(e) or "rien"))
            for et in (r["etages"] or []):
                print("        etage [%-10s] cible u%-3d : utilite=%s  dont feuille TRIGGERED=%.6f"
                      % (et["canal"], et["tgt"], et["u"], et["feuille_triggered"]))
    p, a, s = res["pos"], res["ability"], res["stay"]
    print("  agreement de la marche [canal de PRODUCTION] : pos %d/%d exact, ability %d/%d, "
          "stay %d/%d" % (p["exact"], p["n"], a["match"], a["n"], s["match"], s["n"]))
    print("  le MEME agreement sur le canal NU vaudrait donc : ability %d/%d (les %d decision(s) "
          "deplacee(s) sont la SEULE difference)" % (a["match"] - len(gain) + len(reg), a["n"],
                                                     len(bouge)))

    rc = len(reg)
    if ajouts == 0:
        print("  MUET : le canal n'a rien ajoute de toute la marche -- elle ne prouve RIEN.")
        rc += 1
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL (%d)" % rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
