#!/usr/bin/env python
"""probe_242b -- le cap amis de `FabricatorClawArrayPlaybook` (1006), mesure SANS AUCUN HOOK.

POURQUOI CE SECOND PROBE EXISTE. `probe_242_fabricator_claw_cap.py` lit `X_nat` par decomposition
par etage sur les hooks de `scorer-damage-trace` -- dont les points d'ancrage sont des **RVA
build-specifiques** (`gqfc5mff6c`). Depuis la MAJ `gqfc5mff6c` -> `rnca9r7q6c` ces RVA pointent
ailleurs : le probe REFUSE de tourner, et les re-resoudre exige une REINJECTION (rebuild du bundle),
geste proscrit tant qu'un autre agent partage la session. La question du cap devenait donc
inobservable -- sauf par un instrument qui ne hooke RIEN.

CE QUE CELUI-CI MESURE. Le seul signal natif accessible en RPC pur : **la tuile que l'IA JOUE**
(`aiStepDryRun` -> `MoveUnitMessage`, sans commit). On la confronte aux deux hypotheses :

    H_cap  : terme = w                       (cap `vtbl+0x228` = 1 -> `Min(count, 1)`)
    H_somme: terme = w x #amis retenus        (pas de cap -- ce que le port faisait avant #242)

Sur une candidate a `n` amis retenus, les deux hypotheses ecartent le terme de `w x (n-1)`, soit
**+30 par ami au-dela du premier**. On rapporte, tuile par tuile, le terme sous chaque hypothese et
la SOMME des feuilles du composite Tile(7) du port (`_port_leaves`, la meme que `probe_193c`), donc
les deux argmax et leur MARGE.

CE QU'IL PEUT CONCLURE, ET CE QU'IL NE PEUT PAS. Le natif choisit sur l'utilite TOTALE de l'action,
dont Tile(7) n'est qu'une composante : l'argmax du terme de tuile n'est donc PAS le critere natif.
L'instrument est en TENSION, pas en preuve --
  * si le natif joue une tuile que `H_somme` place derriere la tuile a `n` maximal d'une marge
    superieure a ce que les autres composantes peuvent plausiblement rattraper, `H_somme` est en
    tension et `H_cap` est confortee ;
  * si le natif joue la tuile a `n` maximal, les DEUX hypotheses l'expliquent -> NON DISCRIMINANT.
La preuve du cap reste la mesure `X_nat` de `case-242` par5.1 (18 tuiles, `X_nat` PLAT a 30 pour
`nRep` = 1, 2, 3), obtenue quand les hooks etaient valides.

RESULTAT MESURE (2026-07-29, build `rnca9r7q6c`, `MC1_67`/777) -- **NEGATIF, et c'est l'interet de
ce fichier** : le montage ATTEINT le regime vise (pas 28, candidate `(1,1)` a `nMech = 4, nRep = 3`,
soit exactement le regime `(4,3)` de `case-242` par5.1), mais le natif joue `(5,4)`, une tuile a
`n = 0` que NI `H_cap` NI `H_somme` ne place en tete (leurs argmax sont `(3,2)` et `(1,1)`). Le terme
de tuile n'est donc pas ce qui decide l'action du carrier a ce pas : meme un ecart de **+120** entre
les deux hypotheses ne se lit pas dans le choix. **La voie « argmax sans hook » ne peut pas trancher
le cap sur ce carrier** -- a ranger avec les deux voies deja ecartees en `case-242` par4.1, pour
qu'on ne la re-tente pas. Ce qui reste utilisable ici : le MONTAGE (il produit bien `nRep = 3`) et la
table par tuile, qui restent valables pour un futur re-etalonnage des hooks.

⚠ LE GATE `CanBeRepaired` COMMANDE LA DISCRIMINATION. Le filtre natif exige `HasTrait(u, 5)` **et**
`IBattleQuery.<slot 0x2e = CanBeRepaired>` -- soit, sous ce montage (armure a 0), un ami BLESSE. Tant
qu'aucune candidate n'atteint `nRep >= 2`, les deux hypotheses predisent la MEME chose cote natif et
la mesure ne peut rien dire. C'est pour cela qu'on marche longtemps (`--max-steps`) : le levier n'est
pas la geometrie (le DRIVE donne `nMech = 4` des le tour 1) mais le nombre d'allies BLESSES.

Usage (ASCII only, depuis scripts/python) :
  python probe_242b_fabricator_claw_argmax.py --board MC1_67 --seed 777 --max-steps 140 --extra \
      --hp-target 100000 --hp-player 100000 \
      --p-units "necroSpyder,admecDestroyer,admecManipulus,admecRuststalker,necroDestroyer" \
      --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402
from probe_193c_move_playbook_terms import (_r, _build, _apply_native, _visual_map,  # noqa: E402
                                            _port_leaves)
from probe_242_fabricator_claw_cap import (ABILITY, CARRIER, KEY, MECH_TRAIT,  # noqa: E402
                                           _seed_bc_montage, _drive_cluster, _hp_by_pos, _counts)


class _NoCapPlaybook:
    """`FabricatorClawArrayPlaybook` PRIVE de son cap -- l'hypothese `H_somme`, evaluee cote a cote.

    On ne MUTE pas la classe portee (une mutation globale contaminerait tout le reste du calcul du
    port dans le meme processus) : on instancie une sous-classe dont le seul ecart est
    `MAX_ADJACENT_FRIENDS = None`. Les deux termes sont donc calcules par le MEME code, sur le MEME
    contexte de feuille, a un attribut pres."""

    def __init__(self):
        from engine.playbook.adjacent_unit_preference import FabricatorClawArrayPlaybook

        class _Sum(FabricatorClawArrayPlaybook):
            MAX_ADJACENT_FRIENDS = None

        self.pb = _Sum()

    def term(self, tile, leaf_ctx, wt):
        return self.pb.calculate_movement_utility_in_steps(tile, leaf_ctx, wt)


def _report(sid, rid, ctx, dv, uid, hp, wt, pb, nocap, dry):
    """Table par tuile + les deux argmax + la tuile jouee par le natif. Rend le verdict du pas."""
    msgs = (dry.get("action") or {}).get("messages") or []
    mv = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    mpos = ((me or {}).get("pos") or {})
    origin = (mpos.get("col"), mpos.get("row")) if mpos.get("col") is not None else None
    t_nat = (mv["to"]["col"], mv["to"]["row"]) if mv else origin

    rows = {}
    for t in (ctx.action_tiles or []):
        leaves, leaf_ctx = _port_leaves(ctx, t)
        base = sum(leaves.values()) - leaves.get(8, 0.0) - leaves.get(9, 0.0)
        t_cap = pb.calculate_movement_utility_in_steps(t, leaf_ctx, wt)
        t_sum = nocap.term(t, leaf_ctx, wt)
        nm, nr = _counts(leaf_ctx, t, hp)
        # `base` inclut DEJA le terme sous l'hypothese portee (cap) via la feuille
        # `TriggeredAbilitiesUtility(2)` : on ne l'ajoute pas, on SUBSTITUE l'autre hypothese.
        rows[t] = {"nm": nm, "nr": nr, "cap": t_cap, "sum": t_sum,
                   "x_cap": base, "x_sum": base - t_cap + t_sum}

    if not rows:
        return None
    best_cap = max(rows, key=lambda t: rows[t]["x_cap"])
    best_sum = max(rows, key=lambda t: rows[t]["x_sum"])
    n_max = max(r["nr"] for r in rows.values())

    print("\n===== u%s (%s) origin=%s ; natif joue %s ; %d candidates ====="
          % (uid, (me or {}).get("visualId"), origin, t_nat, len(rows)))
    print("  tuile      nMech nRep  terme_cap terme_somme  X_cap    X_somme")
    for t in sorted(rows, key=lambda t: -rows[t]["x_sum"]):
        r = rows[t]
        print("  %-10s %-5d %-5d %-9.4g %-12.4g %-8.4g %-.4g%s"
              % (t, r["nm"], r["nr"], r["cap"], r["sum"], r["x_cap"], r["x_sum"],
                 "   <== natif" if t == t_nat else ""))
    marge = rows[best_sum]["x_sum"] - rows.get(t_nat, {"x_sum": 0.0})["x_sum"]
    print("  argmax H_cap   = %s (X=%.4g)" % (best_cap, rows[best_cap]["x_cap"]))
    print("  argmax H_somme = %s (X=%.4g)  ; marge sur la tuile NATIVE = %.4g"
          % (best_sum, rows[best_sum]["x_sum"], marge))
    if n_max < 2:
        print("  VERDICT: NON DISCRIMINANT -- nRep max = %d (< 2) : le gate `CanBeRepaired` laisse "
              "les deux hypotheses d'accord cote natif." % n_max)
        return {"discriminant": False, "n_max": n_max}
    if best_cap == best_sum:
        print("  VERDICT: NON DISCRIMINANT -- les deux hypotheses ont le MEME argmax (%s)." % best_cap)
        return {"discriminant": False, "n_max": n_max}
    if t_nat not in (best_cap, best_sum):
        # Cas MESURE le 2026-07-29 (`MC1_67`/777 pas 28, regime (nMech=4, nRep=3)) : le natif joue
        # une tuile a n=0 que NI l'une NI l'autre hypothese ne place en tete. Le terme de tuile
        # n'est donc pas ce qui decide l'action a ce pas -- l'utilite TOTALE est dominee par une
        # autre composante (approche / prediction d'attaque). L'instrument ne peut RIEN conclure :
        # l'ecart de 90 entre les hypotheses est noye. Ne PAS lire ce cas comme un depart.
        print("  VERDICT: NON CONCLUANT -- le natif joue %s, argmax d'AUCUNE des deux hypotheses "
              "(H_cap=%s, H_somme=%s). Le terme de tuile n'est pas decisif a ce pas : le signal "
              "cherche est noye par les autres composantes de l'utilite." % (t_nat, best_cap, best_sum))
        return {"discriminant": False, "n_max": n_max, "t_nat": t_nat,
                "best_cap": best_cap, "best_sum": best_sum, "inconclusive": True}
    verdict = ("H_cap CONFORTEE (le natif joue l'argmax de H_cap, pas celui de H_somme)"
               if t_nat == best_cap else
               "H_somme confortee (le natif joue l'argmax de H_somme)")
    print("  VERDICT: DISCRIMINANT -- %s" % verdict)
    return {"discriminant": True, "n_max": n_max, "t_nat": t_nat,
            "best_cap": best_cap, "best_sum": best_sum, "marge": marge}


def run(sid, rid, max_steps, min_rep):
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.playbook.adjacent_unit_preference import load_playbook

    pb = load_playbook(ABILITY)
    if pb is None:
        print("!! ability %d absente de TRIGGERED_MOVE_PLAYBOOKS" % ABILITY)
        return None
    nocap = _NoCapPlaybook()
    vmap = _visual_map(sid, rid)
    carrier_id = next((k for k, v in vmap.items() if v == CARRIER), None)
    if carrier_id is None:
        print("!! %s absent du runner" % CARRIER)
        return None
    print("carrier u%s (%s) ; on marche jusqu'a nRep >= %d sur une candidate"
          % (carrier_id, CARRIER, min_rep))

    driven, best, seen = set(), None, 0
    for step in range(max_steps):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print("trajectoire native epuisee au pas %d (%s)" % (step, dry.get("error")))
            return best
        uid = dry.get("activatedUnitId")
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
        cu = next((u for u in (dv.get("units") or []) if u.get("id") == carrier_id), None)

        # DRIVE des positions : tant que le carrier a son action, on regroupe les allies autour
        # d'une tuile qu'il peut atteindre puis on TERMINE leur tour (cf. `_drive_cluster`).
        if (step not in driven and cu is not None and cu.get("alive") and cu.get("hasAction")
                and me is not None and me.get("ctrl")):
            allies = [u.get("id") for u in (dv.get("units") or [])
                      if u.get("ctrl") and u.get("alive") and u.get("hasAction")
                      and u.get("id") != carrier_id]
            if allies:
                driven.add(step)
                print("pas %-3d DRIVE (%d allies)" % (step, len(allies)))
                if _drive_cluster(lambda m, b, t=90: _r(sid, m, b, t), rid, carrier_id, allies):
                    continue

        if uid == carrier_id:
            seen += 1
            hp = _hp_by_pos(sid, rid)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            wt = W.load()
            pred = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
            ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt, pred)
            pairs = sorted({_counts(_port_leaves(ctx, t)[1], t, hp)
                            for t in (ctx.action_tiles or [])})
            print("pas %-3d activation #%d du carrier : (nMech,nRep) = %s" % (step, seen, pairs))
            got = _report(sid, rid, ctx, dv, uid, hp, wt, pb, nocap, dry)
            if got:
                best = got if (best is None or got["n_max"] > best["n_max"]) else best
                if got["discriminant"] and got["n_max"] >= min_rep:
                    return got
        _apply_native(sid, rid, dry)
    print("aucun pas discriminant en %d pas (%d activations du carrier)" % (max_steps, seen))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--max-steps", type=int, default=140)
    ap.add_argument("--min-rep", type=int, default=2)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    a = ap.parse_args()
    # AUCUN gate de build : ce probe ne hooke rien (c'est sa raison d'etre).
    sid = _resolve_session()
    if a.runner is not None:
        return 0 if run(sid, a.runner, a.max_steps, a.min_rep) else 1
    seed_bc = _seed_bc_montage(Path(__file__).resolve().parents[2]
                               / "logs" / "runners" / "a242b-seed-bc.json")
    rid, state = _build(a.seed, a.board, list(a.extra or []) + ["--seed-bc", str(seed_bc)])
    if rid is None:
        return 1
    print("runner %d seed=%s board=%s carrier=%s" % (rid, a.seed, a.board, CARRIER))
    try:
        return 0 if run(sid, rid, a.max_steps, a.min_rep) else 1
    finally:
        if not a.keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            try:
                state.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
