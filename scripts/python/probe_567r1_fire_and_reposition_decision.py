"""#567-r1 -- face DECISION de `1063 FireAndReposition` (`eldarRanger` << Calandis >>).

LE CRITERE, ENONCE AVANT LE MONTAGE
------------------------------------
`FireAndRepositionPlaybook$$EvaluateNonComparable` :

    u(position) = 3/2 + 20 * GetAverageDistance(position, tous les ennemis vivants) + Tile(7)(position)

Le terme dominant est la DISTANCE MOYENNE aux ennemis, depuis la tuile de CAST -- et il ne depend
PAS de la cible (`entities@+0x40` = `possibleCasterTile`, offset LU dans
`BasePlaybook$$GetEligibleTargetsSelectable`). Calandis est une tireuse a qui l'ability REND son
deplacement : le natif la pousse donc a tirer depuis la position la plus RECULEE d'ou la cible
reste legale. C'est un OBSERVABLE fort et facile a falsifier -- l'inverse d'un terme constant.

  * `recul`       -- ennemi AU CONTACT. Le natif doit proposer 1063 avec un DEPLACEMENT vers une
                     tuile STRICTEMENT plus loin de l'ennemi que son origine. Un port qui casterait
                     en place (ou qui avancerait) diverge ici.
  * `attribution` -- MEME caster, ennemi DEPLACE en (1,4). Ce bras existe parce que le premier ne
                     suffit PAS, et la mesure le dit : sur le banc `recul`, CINQ positions
                     eligibles atteignent la MEME utilite 91.5 (le terme `20*d` et `Tile(7)` se
                     compensent exactement), donc c'est le keep-first qui tranche et l'accord n'est
                     ATTRIBUABLE a rien. Le placement de `attribution` est choisi sur la table
                     `Tile(7)` MESUREE du board pour que l'argmax soit **STRICT** (marge 30) et
                     tombe sur une tuile que `Tile(7)` seul ne designerait PAS en premier.

CONTRE-EPREUVES (port, MEME etat), chacune retire UNE lecture :

  * `signe`      -- poids `-20` au lieu de `+20` : le port doit choisir une AUTRE tuile (la plus
                    PROCHE). Sans cette morsure, l'accord pourrait venir d'un terme constant.
  * `sans_terme` -- poids `0` : le terme de distance disparait, il ne reste que `1.5 + Tile(7)`.
                    Elle etablit que c'est bien la DISTANCE qui choisit la tuile, et pas le relief.
                    ⚠ Elle est NON DISCRIMINANTE sur `recul` (mesure ci-dessus) -- le probe le DIT
                    au lieu de le taire, et n'exige la morsure que sur `attribution`.

ORACLE = `aiDryRunAllUnits` (`CalculateNextActionForUnit`, read-only, `mutated=false` verifie).

ASCII only (cp1252). Usage (depuis scripts/python, session Frida chaude) :
    python probe_567r1_fire_and_reposition_decision.py [--seed 56701] [--board MC1_67] [--garder]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from probe_119_supreme_commander_decision import native_proposal, port_proposal, r  # noqa: E402
from rl_collect_batch import _resolve_session                                       # noqa: E402

FIRE_AND_REPOSITION = 1063
CASTER = "eldarRanger"
FOE = "tauCrisis"
BOARD = "MC1_67"
RANK = 17

#: Calandis part au CONTACT de l'ennemi : toute tuile de recul augmente la distance, donc l'argmax
#: ne peut PAS etre l'origine -- c'est ce qui rend le bras discriminant.
POS_CASTER = (3, 4)
POS_FOE = (4, 4)
#: Bras `attribution` : place CHOISIE sur la table `Tile(7)` mesuree du board pour rendre l'argmax
#: STRICT. Avec l'ennemi ici, `(4,2)` (d=3, T7=50) vaut `1.5 + 60 + 50 = 111.5` contre `81.5` a la
#: seconde -- marge 30 -- alors que `Tile(7)` SEUL laisse `(2,3)` et `(4,2)` a EGALITE (T7=50 tous
#: les deux), donc le keep-first prend `(2,3)`, qui precede `(4,2)` dans `reach_nc`.
POS_FOE_ATTRIB = (1, 4)
POS_ARGMAX_ATTENDU = (4, 2)


def _tile(p):
    return "%d,%d" % (p[0], p[1])


def _duel(args, timeout=400):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def build(state_file: str, seed: int, board: str, pos_foe=POS_FOE):
    argv = ["build", "--seed", str(seed), "--board", board, "--rank", str(RANK),
            "--p-units", CASTER, "--a-units", FOE, "--no-ai",
            "--place", "%s:%s" % (CASTER, _tile(POS_CASTER)),
            "--a-place", "%s:%s" % (FOE, _tile(pos_foe)),
            "--state-file", state_file]
    p = _duel(argv)
    if p.returncode != 0 or not os.path.exists(state_file):
        print("[build] rc=%s\n%s\n%s" % (p.returncode, (p.stdout or "")[-1800:],
                                         (p.stderr or "")[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def _par_position(sid, rid):
    dv = r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[(p.get("col"), p.get("row"))] = u
    return out, dv


def assert_montage(par_pos, pos_foe):
    c = par_pos.get(POS_CASTER)
    if c is None or c.get("visualId") != CASTER:
        raise SystemExit("caster ABSENT de %r (vu %r)" % (POS_CASTER, (c or {}).get("visualId")))
    f = par_pos.get(pos_foe)
    if f is None or f.get("visualId") != FOE:
        raise SystemExit("ennemi ABSENT de %r (vu %r)" % (pos_foe, (f or {}).get("visualId")))
    return c["id"], f["id"]


def _port_avec_poids(sid, rid, uid, poids):
    """MEME decision, terme de distance repondere. `0` = terme neutralise, `-20` = signe inverse."""
    from engine.playbook.noncomparable.fire_and_reposition import FireAndRepositionPlaybook as FR
    ancien = FR._DISTANCE_WEIGHT
    FR._DISTANCE_WEIGHT = poids
    try:
        return port_proposal(sid, rid, uid)
    finally:
        FR._DISTANCE_WEIGHT = ancien


def decompose(sid, rid, uid):
    """DIAGNOSTIC par ETAGE (pas un oracle) : pour chaque position candidate, `(distance moyenne,
    terme de distance, Tile(7), utilite)`. C'est ce qui dit si l'accord est ATTRIBUABLE au terme de
    distance ou si `Tile(7)` suffirait a le produire seul."""
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook import scene as _scene
    from engine.playbook.base import tile_utility
    from engine import weights
    dv = r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: r(sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: r(sid, m, b, t), rid, dv, mov_by_unit, uid,
                      weights.load(), predictor)
    nc = PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, wt=c.wt, obs_units=c.obs_units, units=c.units,
        ability_targets=c.ability_targets, is_temporary_by_pos=c.is_temporary_by_pos,
        effects_by_pos=c.effects_by_pos, tile_id_by_pos=c.tile_id_by_pos, scene=c.scene,
        cast_from_tiles=c.cast_from_tiles)
    pb = PB.PLAYBOOKS[FIRE_AND_REPOSITION]
    # Positions REELLEMENT eligibles (mirror `GetEligibleTargetsSelectable` position par position) --
    # sans elles, la table melangerait des tuiles que le generateur n'atteint jamais, et un
    # << argmax >> lu dessus serait faux.
    eligibles = set()
    for ev in ((nc.plan or {}).get("evals") or []):
        if ev.get("abilityId") != pb.ABILITY_ID or not ev.get("rankCount"):
            continue
        rset = {(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
                if rk.get("col") is not None}
        if rset:
            eligibles |= pb.eligible_positions(nc, ev.get("targetId"), rset, ev)
    lignes = []
    for P in (nc.reach_nc or []):
        d = pb._average_distance_to_enemies(P, nc)
        t7 = tile_utility(nc, P)
        lignes.append((P, P in eligibles, d, None if d is None else d * pb._DISTANCE_WEIGHT,
                       round(t7, 2),
                       None if d is None else round(1.5 + d * pb._DISTANCE_WEIGHT + t7, 2)))
    return lignes


def _dist(a, b):
    from engine.battle_query import hexgeo
    if a is None or b is None or a[0] is None or b[0] is None:
        return None
    return hexgeo.distance((a[0], a[1]), (b[0], b[1]))


def confronte(tag, sid, rid, uid, pos_foe, argmax_attendu=None):
    nat = native_proposal(sid, rid, uid)
    port = port_proposal(sid, rid, uid)
    signe = _port_avec_poids(sid, rid, uid, -20)
    sans = _port_avec_poids(sid, rid, uid, 0)
    nat_cast = nat["ability"] == FIRE_AND_REPOSITION
    port_cast = port.get("kind") == "ability" and port.get("ability") == FIRE_AND_REPOSITION
    d_nat = _dist(nat.get("move"), pos_foe)
    d_org = _dist(POS_CASTER, pos_foe)
    ok = (nat_cast and port_cast and nat.get("move") == port.get("to")
          and d_nat is not None and d_org is not None and d_nat > d_org)
    if argmax_attendu is not None:
        # Le montage a ete CHOISI pour que l'argmax tombe ici : s'il tombe ailleurs, ce n'est pas
        # << le port a tort >>, c'est << ce banc ne mesure pas ce qu'il annonce >>.
        ok = ok and nat.get("move") == argmax_attendu
    print("[%s] u%s  NATIF(ab=%s tgt=u%s move=%r d=%s)  PORT(%s ab=%s tgt=u%s to=%r)"
          % (tag, uid, nat["ability"], nat["target"], nat.get("move"), d_nat,
             port.get("kind"), port.get("ability"), port.get("target"), port.get("to")))
    print("       origine=%r d=%s ; attendu=%r ; CONTRE-EPREUVES : poids -20 -> to=%r ; "
          "poids 0 -> to=%r  -> %s"
          % (POS_CASTER, d_org, argmax_attendu, signe.get("to"), sans.get("to"),
             "OK" if ok else "DESACCORD"))
    lignes = decompose(sid, rid, uid)
    print("       DECOMPOSITION des positions ELIGIBLES (position, dist, 20*d, Tile7, utilite) :")
    for l in sorted([x for x in lignes if x[1]], key=lambda x: -(x[5] or 0))[:6]:
        print("         %r  d=%s  20d=%s  T7=%s  u=%s" % (l[0], l[2], l[3], l[4], l[5]))
    return {"tag": tag, "natif": nat, "port": port, "signe": signe, "sans_terme": sans,
            "d_natif": d_nat, "d_origine": d_org, "decomposition": lignes, "ok": ok}


def campagne(sid, sf, seed, board, garder=False):
    """Les DEUX bras, chacun sur SON runner (les placements different). FOYER UNIQUE du montage et
    des criteres : `main` et la garde `test_567_fire_and_reposition_live.py` passent par ici."""
    recs = []
    for tag, pos_foe, attendu in (("recul", POS_FOE, None),
                                  ("attribution", POS_FOE_ATTRIB, POS_ARGMAX_ATTENDU)):
        sfx = sf.replace(".json", "_%s.json" % tag)
        rid = build(sfx, seed, board, pos_foe)
        if rid is None:
            print("[567r1] BUILD KO (%s)" % tag)
            return recs
        try:
            par_pos, _dv = _par_position(sid, rid)
            uid, fid = assert_montage(par_pos, pos_foe)
            print("[567r1] %s : runner=%s  Calandis=u%s@%s  ennemi=u%s@%s"
                  % (tag, rid, uid, POS_CASTER, fid, pos_foe))
            recs.append(confronte(tag, sid, rid, uid, pos_foe, attendu))
        finally:
            if not garder:
                _duel(["dispose", "--state-file", sfx, "--runner", str(rid)], timeout=120)
    return recs


def verdict(recs) -> bool:
    """`True` ssi les DEUX bras concordent ET les deux contre-epreuves MORDENT sur `attribution`.

    Sur `recul` la contre-epreuve `poids 0` n'est PAS exigee : la decomposition y montre un TIE a
    cinq positions, donc elle ne PEUT pas mordre -- l'exiger la ferait echouer un banc juste."""
    if len(recs) < 2:
        print("[567r1] montage sterile : %d bras sur 2" % len(recs))
        return False
    ok = all(rec["ok"] for rec in recs)
    for rec in recs:
        ms = rec["signe"].get("to") != rec["port"].get("to")
        m0 = rec["sans_terme"].get("to") != rec["port"].get("to")
        print("[567r1] %-11s contre-epreuves : poids -20 -> %s ; poids 0 -> %s"
              % (rec["tag"], "MORD" if ms else "NON DISCRIMINANTE",
                 "MORD" if m0 else "NON DISCRIMINANTE"))
        if rec["tag"] == "attribution":
            if not ms:
                print("            => le terme de distance n'est pas ce qui choisit la tuile")
            if not m0:
                print("            => `Tile(7)` seul rendrait la MEME tuile : ce banc n'attribue "
                      "RIEN au terme de distance")
            ok = ok and ms and m0
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Face DECISION de 1063 -- le terme de distance")
    ap.add_argument("--seed", type=int, default=56701)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--garder", action="store_true")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    sf = a.state_file or str(PYDIR.parents[1] / "logs" / ("probe567r1_%d.json" % os.getpid()))
    recs = campagne(sid, sf, a.seed, a.board, garder=a.garder)
    ok = verdict(recs)
    print("[567r1] VERDICT : %s" % ("OK" if ok else "DESACCORD"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
