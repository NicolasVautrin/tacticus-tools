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

    python probe_202r_decision_abraxas.py [--steps 40] [--seed 20203[,31337,...]]

⚠ `#202-r1` -- LE SOMMET DU SWEEP EST UN EX AEQUO, ET LE PROBE LE DIT MAINTENANT. Le verdict
d'origine (<< SWEEP DISCRIMINANT : 8 valeurs d'utilite >>) est vrai et INSUFFISANT : plusieurs
couples (position, tuile de spawn) atteignaient l'utilite MAXIMALE 141, donc l'accord du port avec
le natif etait COMPATIBLE avec sa regle de tie-break (`strict >` = 1re paire enumeree) sans la
PROUVER. Deux ajouts :

  * le sommet est desormais VENTILE (couples, tuiles distinctes) et le probe distingue TROIS
    regimes : sommet UNIQUE (accord probant), sommet ex aequo mais TUILE unique (la cible emise ne
    depend d'aucun tie-break), sommet ex aequo sur plusieurs TUILES (le cas de `#202-r1`) ;
  * `--seed` accepte une LISTE : le probe joue les geometries l'une apres l'autre, UN runner
    vivant a la fois, et s'arrete des qu'un sommet UNIQUE apparait. C'est exactement le geste que
    la fiche reclame (<< crafter une geometrie ou le sommet est UNIQUE >>).

⚠ Et l'ORDRE du sweep a change (`#971-r4`) : le port enumere les tuiles de spawn PAR POSITION
(`fromHere` a l'origine, liste d'adjacence STOCKEE ailleurs) et non plus dans l'ordre de l'UNION du
RPC. L'instrumentation ci-dessous rejoue le MEME ordre -- sinon elle mesurerait un sweep que le
port n'emprunte plus.

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
    from engine.playbook.noncomparable._base import (eligible_target_tiles,
                                                     tiles_in_native_order)
    from engine.playbook.noncomparable.master_of_the_tutelaries import (
        MasterOfTheTutelariesPlaybook as PB)

    journal = []
    vrai = PB.generate_candidates

    def _instrumente(self, ctx):
        detail = []
        # `#971-r4` : le sweep suit desormais l'ORDRE PAR POSITION (fromHere a l'origine, liste
        # d'adjacence STOCKEE ailleurs). L'instrumentation le rejoue a l'identique -- sinon elle
        # mesurerait un ordre que le port n'emprunte plus.
        from_here, union = eligible_target_tiles(ctx, PB.ABILITY_ID)
        spawn_tiles = from_here or union
        eligibles = set(from_here) | set(union)
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
                for ST in tiles_in_native_order(ctx, T, from_here, union, eligibles):
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


def _passe(a, seed: str) -> tuple:
    """UNE passe complete (build -> walk -> dispose) pour une seed. Rend `(rc, unique)`.

    `unique` = le sommet du sweep est-il ATTEINT PAR UN SEUL couple (position, tuile de spawn) ?
    C'est le cran de `#202-r1` : tant que le sommet est EX AEQUO, l'accord avec le natif ne
    prouve pas la regle de tie-break -- il est compatible avec elle, ce qui n'est pas la meme
    chose."""
    pydir = REPO / "scripts" / "python"
    sf = REPO / "logs" / "runners" / ("p202r-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", str(sf),
         "--board", BOARD, "--roster", "1", "--p-units", P_UNITS, "--a-units", A_UNITS],
        cwd=str(pydir), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("build KO : %s" % (proc.stderr or proc.stdout or "")[-400:])
        return 1, False
    rid = int(json.loads(sf.read_text())["runnerId"])
    print("[202r] runner %d, board %s, seed %s" % (rid, BOARD, seed))

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
        return 1, False

    rc = 0
    unique = False
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
        # `#202-r1` -- LE SOMMET EST-IL UNIQUE ? Un `[MATCH]` sur un sommet EX AEQUO est
        # COMPATIBLE avec la regle de tie-break du port, il ne la PROUVE pas : c'est toute la
        # difference que le residu nomme. On l'imprime au lieu de la taire.
        if retenus:
            top = max(d["util"] for d in retenus)
            sommet = [d for d in retenus if d["util"] == top]
            couples = sorted({(d["pos"], d["spawn"]) for d in sommet})
            tuiles = sorted({d["spawn"] for d in sommet})
            if len(couples) == 1:
                unique = True
                print("        SOMMET UNIQUE : u=%.0f atteint par le SEUL couple %r -- l'accord "
                      "avec le natif est PROBANT sans rien supposer du tie-break." % (top,
                                                                                      couples[0]))
            elif len(tuiles) == 1:
                unique = True
                print("        SOMMET EX AEQUO mais TUILE UNIQUE : u=%.0f atteint par %d couples, "
                      "tous sur la tuile %r -- la CIBLE emise ne depend d'aucun tie-break (seule "
                      "la position le ferait)." % (top, len(couples), tuiles[0]))
            else:
                print("        SOMMET EX AEQUO : u=%.0f atteint par %d couples sur %d tuiles "
                      "DISTINCTES %r -- l'accord est COMPATIBLE avec le tie-break `strict >` "
                      "(1re paire enumeree), il ne le PROUVE pas. C'est `#202-r1`."
                      % (top, len(couples), len(tuiles), tuiles))
    print("\n[202r] rc=%d -- l'agreement pas-a-pas (dont la ligne `ab=%d`) est imprime ci-dessus "
          "par `engine_validate`." % (rc, ABILITY))
    return rc, unique


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--seed", default="20203",
                    help="une seed, ou plusieurs SEPAREES PAR DES VIRGULES : le probe les joue "
                         "l'une apres l'autre (UN runner vivant a la fois) et s'arrete des qu'une "
                         "geometrie rend le SOMMET UNIQUE -- c'est le geste que `#202-r1` reclame.")
    a = ap.parse_args(argv)

    seeds = [s.strip() for s in str(a.seed).split(",") if s.strip()]
    dernier = 1
    for s in seeds:
        rc, unique = _passe(a, s)
        dernier = rc
        if unique:
            print("\n[202r] SOMMET UNIQUE atteint sur la seed %s -- la mesure est PROBANTE, "
                  "`#202-r1` peut se fermer." % s)
            return rc
        print("\n[202r] seed %s : sommet EX AEQUO, on essaie la suivante." % s)
    print("\n[202r] AUCUNE des %d seed(s) n'a rendu un sommet UNIQUE -- `#202-r1` reste OUVERT, "
          "et ce n'est PAS un desaccord de port." % len(seeds))
    return dernier


if __name__ == "__main__":
    raise SystemExit(main())
