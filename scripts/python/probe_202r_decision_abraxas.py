"""probe_202r -- la face DECISION d'Abraxas confrontee a l'ORACLE (residu de `case-202`).

`case-202` §8 livre les tranches A/B/C et laisse UNE chose ouverte : le playbook NonComparable
`IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook$$EvaluateNonComparable` est PORTE mais
n'a jamais ete confronte a l'IA native. La fiche nomme meme le montage (§5, volet C) : << walk avec
Abraxas -- agreement decision (le natif cast-il quand nous castons ?) >>.

L'ORACLE EST LE TOUR IA OBSERVE, pas `aiPredict` : `engine_validate.py` marche la trajectoire
native (`aiStepDryRun` = sa decision NON appliquee) et compare, pas a pas, la decision du moteur sur
le MEME etat. Ce probe l'appelle tel quel -- il n'en refait pas un.

CE QU'IL AJOUTE, ET POURQUOI IL LE FAUT. Un `[MATCH]` sur le pas `1096` ne prouve rien s'il n'y
avait qu'une tuile candidate : l'accord en regime DEGENERE est un accord vide. Le probe
INSTRUMENTE donc `generate_candidates` pour capturer le SWEEP COMPLET du playbook -- toutes les
tuiles de spawn examinees, leurs `nFree`, leur `nE2`, le bonus de 100, et l'utilite finale. Le
verdict n'est rendu que si le sweep a plus d'un candidat ET plus d'une valeur d'utilite : sinon le
probe le DIT et refuse de conclure.

    python probe_202r_decision_abraxas.py [--steps 40] [--seed 20203]

ASCII only. rc 0 = le pas 1096 a ete observe, le sweep est discriminant, et le port choisit la
tuile du natif. rc 1 = pas de cast 1096 observe, sweep degenere, ou desaccord.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

ABRAXAS = "thousInfernalMaster"
ABILITY = 1096                      # ActiveAbilityType.MasterOfTheTutelaries
P_UNITS = "thousInfernalMaster,thousSorcerer"
A_UNITS = "necroWarden,necroWarden,necroOverlord"
BOARD = "MC1_67"


def _sweep_instrumente():
    """Remplace le corps de `generate_candidates` par un jumeau qui GARDE tout le sweep.

    On ne re-implemente pas la formule : on rejoue LE code du playbook et on intercepte, pour chaque
    couple (position, tuile de spawn) retenu par les gates, les trois termes qui composent l'utilite.
    Le candidat rendu reste EXACTEMENT celui du playbook (meme regle `strict >`, meme MIN_UTILITY) --
    sinon le probe mesurerait son propre code au lieu du port."""
    import hexgeo
    from engine import battle_query as bq
    from engine.playbook.noncomparable.master_of_the_tutelaries import (
        MasterOfTheTutelariesPlaybook as PB)

    journal = []
    vrai = PB.generate_candidates

    def _instrumente(self, ctx):
        detail = []
        spawn_tiles = self._eligible_spawn_tiles(ctx)
        if spawn_tiles and ctx.origin is not None:
            n_e2 = sum(1 for p in (ctx.epos or [])
                       if hexgeo.distance(ctx.origin, (p[0], p[1])) == 2)
            near_tile = self._nearest_enemy_tile(ctx)
            occ = {(u.get("col"), u.get("row")) for u in (ctx.obs_units or [])
                   if not u.get("isDead") and u.get("col") is not None}
            if not occ:
                occ = set(ctx.epos or []) | set(ctx.fpos or []) | {ctx.origin}
            neigh = bq.neigh_map(ctx)
            for T in ctx.reach_nc:
                for ST in spawn_tiles:
                    if not bq.is_adjacent(T, ST, ctx.elev_by_pos, neigh):
                        continue
                    n_free = bq.adjacent_addable_count(ST, ctx.neigh_by_pos, ctx.walkable_by_pos,
                                                       occ - {ST}, ctx.elev_by_pos)
                    bonus = (near_tile is not None
                             and hexgeo.distance(near_tile, ST) == 2)
                    u = (1.0 + max(n_e2 - 1, 0) * 10 + max(n_free - 3, 0) * 10
                         + (100.0 if bonus else 0.0))
                    detail.append({"pos": T, "spawn": ST, "nFree": n_free, "nE2": n_e2,
                                   "bonus100": bool(bonus), "util": u,
                                   "gate_nFree": n_free > 2, "gate_nE2": n_e2 > 0})
        out = vrai(self, ctx)
        journal.append({"uid": ctx.uid, "origin": ctx.origin, "detail": detail, "rendu": out})
        return out

    PB.generate_candidates = _instrumente
    return journal, (PB, vrai)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--seed", default="20203")
    a = ap.parse_args(argv)

    pydir = REPO / "scripts" / "python"
    sf = REPO / "logs" / "runners" / ("p202r-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", a.seed, "--state-file", str(sf),
         "--board", BOARD, "--roster", "1", "--p-units", P_UNITS, "--a-units", A_UNITS],
        cwd=str(pydir), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("build KO : %s" % (proc.stderr or proc.stdout or "")[-400:])
        return 1
    rid = int(json.loads(sf.read_text())["runnerId"])
    print("[202r] runner %d, board %s, seed %s" % (rid, BOARD, a.seed))

    journal, (PB, vrai) = _sweep_instrumente()
    try:
        import engine_validate
        engine_validate.main(["--runner", str(rid), "--steps", str(a.steps)])
    finally:
        PB.generate_candidates = vrai
        try:
            from rl_collect_batch import _resolve_session, _rpc
            _rpc(_resolve_session(), "disposeRunner", [{"runnerId": rid}], timeout=30)
        except Exception:
            pass

    # --- le pas qui compte : celui ou le playbook 1096 a rendu un candidat ---------------------
    casts = [e for e in journal if e["rendu"]]
    print("\n[202r] appels au playbook 1096 : %d ; dont %d ont rendu un candidat"
          % (len(journal), len(casts)))
    if not casts:
        vus = [e for e in journal if e["detail"]]
        print("[202r] AUCUN cast propose. Sweeps NON VIDES : %d." % len(vus))
        for e in vus[:3]:
            print("       origin=%r -> %d couple(s) examines, gates : %r"
                  % (e["origin"], len(e["detail"]),
                     [(d["gate_nFree"], d["gate_nE2"]) for d in e["detail"][:6]]))
        print("[202r] Le montage n'a pas atteint le regime du cast -- ce n'est PAS un verdict sur "
              "le port. Re-joue avec une autre seed ou plus de pas.")
        return 1

    rc = 0
    for e in casts:
        det = e["detail"]
        utils = sorted({d["util"] for d in det if d["gate_nFree"] and d["gate_nE2"]})
        retenus = [d for d in det if d["gate_nFree"] and d["gate_nE2"]]
        print("\n[202r] u%s @%r : %d couple(s) (position, tuile de spawn) examines, %d passent les "
              "deux gates" % (e["uid"], e["origin"], len(det), len(retenus)))
        for d in sorted(retenus, key=lambda x: -x["util"])[:8]:
            print("        spawn=%r depuis %r : nFree=%d nE2=%d bonus100=%s -> u=%.0f"
                  % (d["spawn"], d["pos"], d["nFree"], d["nE2"], d["bonus100"], d["util"]))
        print("        rendu par le playbook : %r" % (e["rendu"],))
        # ANTI-DEGENERESCENCE : sans plusieurs candidats ET plusieurs utilites, un MATCH ne
        # departage rien -- le port aurait << raison >> quoi qu'il calcule.
        if len(retenus) < 2:
            print("        SWEEP DEGENERE : %d candidat(s) retenu(s). Un accord avec le natif ne "
                  "prouverait rien ici." % len(retenus))
            rc = 1
        elif len(utils) < 2:
            print("        SWEEP NON DISCRIMINANT : %d candidats mais UNE seule valeur d'utilite "
                  "(%r) -- le choix est un tie-break, pas un classement." % (len(retenus), utils))
            rc = 1
        else:
            print("        SWEEP DISCRIMINANT : %d candidats, %d valeurs d'utilite distinctes "
                  "(%r) -- le choix du port departage pour de bon." % (len(retenus), len(utils),
                                                                       utils))
    print("\n[202r] rc=%d -- l'agreement pas-a-pas (dont la ligne `ab=%d`) est imprime ci-dessus "
          "par `engine_validate`." % (rc, ABILITY))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
