"""#443-r2-b1 -- ce que la bascule du canal DEPLACE, paire par paire, contre l'oracle natif.

LE CRITERE, AVANT LA METHODE
----------------------------
Fermer le `-35` de #501 ne suffit pas : une correction juste peut casser autre chose. La question
binaire est donc DOUBLE, et elle se mesure sur le MEME balayage :

  (a) la paire du montage de #501 se referme-t-elle ?           -> GAIN attendu
  (b) une AUTRE paire se deplace-t-elle ?                       -> et si oui, vers ou ?

Le critere de deplacement est l'ecart entre les DEUX CANAUX DU PORT (`decisionView` nu contre
`decision_view_seed_body`), jamais l'ecart au natif -- exactement comme la contre-epreuve de #501.
Le natif, lui, sert d'ARBITRE : pour chaque paire qui bouge, on dit si le mouvement RAPPROCHE du
natif (GAIN) ou l'en ECARTE (REGRESSION). Une paire qui ne bouge pas est un resultat, pas un vide.

⚠ Sur un effet ACTIF les deux canaux COINCIDENT -- c'est ce qui a rendu la contre-epreuve `CE3` de
#443 muette. Le balayage joue donc les DEUX regimes : etat au tour du caster (overwatch ARME) puis,
apres un `endturn`, etat au tour du porteur (overwatch INERTE). Sans le second cran, ce probe ne
mesurerait rien.

CE QU'IL BALAYE
---------------
Toutes les paires (caster controle, cible ennemie, tuile candidate) a l'ATTAQUE NORMALE -- le meme
instrument que #501 (`NORMAL_ATTACK_PLAYBOOK.calculate_action_utility` contre le RPC `pairUtility`).
Le contexte du port est bati UNE fois par (caster, canal) ; le natif est interroge UNE fois par
paire (il ne depend d'aucun canal de port).

Usage :
    python probe_443r2b1_pair_sweep.py --state-file <ABSOLU> [--board B] [--seed S]
                                       [--p-units a,b,c] [--a-units x,y,z] [--tiles N]

rc = nombre de paires qui ont bouge SANS que le natif les arbitre en GAIN. ASCII only.
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

import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
import probe_443r2_only_active_overwatch as P501                 # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402
from engine.runner.snapshot import decision_view_seed_body       # noqa: E402

EPS = 1e-4
#: Roster par defaut : le montage de #501 ELARGI. `emperNoiseMarine` porte `SuppressiveFire` (le
#: call-site `onlyActive = 0`), `eldarRanger` porte l'overwatch 1009 ET le filet 1111 -- les deux
#: effectTypes que le rayon de souffle de #501 a mesures. Les autres sont du BRUIT VOULU : ce sont
#: eux qui repondent a « une AUTRE paire bouge-t-elle ? ».
P_UNITS = "emperNoiseMarine,ultraEliminatorSgt,bloodDeathCompany"
A_UNITS = "eldarRanger,tauCrisis,orksWarboss"


class MontageError(RuntimeError):
    pass


def _build(state_file: str, board: str, seed: str, p_units: str, a_units: str) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file,
            "--board", board, "--p-units", p_units, "--a-units", a_units,
            "--hp-target", "90000", "--hp-player", "90000"]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _dv(rpc, rid: int, seed_inactive: bool) -> dict:
    """LES DEUX CANAUX, par la porte NOMMEE quand c'est celui du seed."""
    body = (decision_view_seed_body(rid, allAbilities=True, maxRank=32) if seed_inactive
            else {"runnerId": rid, "allAbilities": True, "maxRank": 32})
    return rpc("decisionView", body, 180)


def _ctx(rpc, rid: int, cid: int, seed_inactive: bool, predictor):
    dv = _dv(rpc, rid, seed_inactive)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), predictor)


def _stage(sid, rpc, rid: int, gap: int = 4) -> dict:
    """DEUX AMAS SEPARES, pas deux anneaux concentriques.

    La 1re version placait les amis sur l'anneau 3 et les ennemis sur l'anneau 4 du MEME centre :
    des paires ADJACENTES en sortaient, et le predicat natif de `SuppressiveFire` est NIE au contact
    (`if (!AreEntitiesAdjacent(tile, target))`) -- le terme discriminant n'entrait donc dans AUCUNE
    paire, et le balayage rendait « 0 bouge » pour une raison de GEOMETRIE, pas de mecanique.
    C'est le vice « bloque par la geometrie de spawn » : on PILOTE les positions.

    Ici : amis dans le disque de rayon 1 autour de `A`, ennemis dans celui autour de `B`, avec
    `distance(A, B) = gap` -> toute distance croisee est dans `[gap-2, gap+2]`, donc >= 2 pour
    `gap >= 4`. Les distances effectives sont IMPRIMEES : la geometrie est attestee, pas supposee."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee vivante")
    myplayer = mine[0].get("owner")
    foes = [u for u in units if u.get("owner") != myplayer and u.get("alive")]
    if not foes:
        raise MontageError("montage NON INSTALLE : aucun adversaire vivant")
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    a = min(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2)
    cand_b = [p for p in cells if hexgeo.distance(a, p) == gap]
    if not cand_b:
        raise MontageError(f"montage NON INSTALLE : aucune tuile a distance {gap} de {a}")
    for b in cand_b:
        amas_a = [p for p in cells if hexgeo.distance(a, p) <= 1
                  and hexgeo.distance(b, p) >= gap - 1]
        amas_b = [p for p in cells if hexgeo.distance(b, p) <= 1
                  and hexgeo.distance(a, p) >= gap - 1]
        if len(amas_a) >= len(mine) and len(amas_b) >= len(foes):
            break
    else:
        raise MontageError(f"montage NON INSTALLE : aucun couple d'amas de rayon 1 a distance {gap}")
    want = {u["id"]: amas_a[i] for i, u in enumerate(mine)}
    want.update({u["id"]: amas_b[i] for i, u in enumerate(foes)})
    if not P124._drive_to(sid, rid, walk, elev, want):
        _d, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {want}, "
                           f"obtenu { {u: pos.get(u) for u in want} }")
    P124._give_turn_back(sid, rid, myplayer)
    dmin = min(hexgeo.distance(want[m["id"]], want[f["id"]]) for m in mine for f in foes)
    dmax = max(hexgeo.distance(want[m["id"]], want[f["id"]]) for m in mine for f in foes)
    print("  geometrie ATTESTEE : amas %s / %s (gap %d) -> distances croisees %d..%d"
          % (a, b, gap, dmin, dmax))
    if dmin < 2:
        raise MontageError("montage DEGENERE : une paire est au CONTACT -- le predicat natif de "
                           "`SuppressiveFire` y est NIE, le terme discriminant n'entrerait pas")
    return {"rid": rid, "player": myplayer,
            "mine": [u["id"] for u in mine], "foes": [u["id"] for u in foes]}


def blast(rpc, rid: int, regime: str) -> int:
    """Ce que le canal AJOUTE sur CET etat -- l'ANTI-MUET du balayage.

    « 0 paire ne bouge » ne vaut RIEN si le canal n'ajoutait rien : c'est exactement le vice de la
    contre-epreuve `CE3` de #443. On MESURE donc l'ajout, regime par regime, et le balayage ECHOUE
    s'il est nul partout."""
    br = P501.blast_radius(rpc, rid)
    n = br["entrees_include"] - br["entrees_defaut"]
    print("  [%s] rayon de souffle du canal : entrees %d -> %d (+%d) sur %d unite(s) %s"
          % (regime, br["entrees_defaut"], br["entrees_include"], n, br["unites_touchees"],
             sorted("%s(%s)" % (nom, t) for (t, nom) in br["par_type"])))
    return n


def sweep(rpc, rid: int, case: dict, n_tiles: int, regime: str) -> list[dict]:
    """Une ligne par (caster, cible, tuile) : natif + port sur les DEUX canaux."""
    predictor = _scene.build_predictor(rpc, rid)
    if predictor is None:
        raise MontageError("combatSnapshot KO -- le predicteur offline est indisponible")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = {u["id"]: u for u in (dv.get("units") or [])}
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by = {u.get("unitId"): u for u in (mov.get("units") or [])}
    rows = []
    for cid in case["mine"]:
        me = units.get(cid)
        if me is None or not me.get("alive") or not me.get("pos"):
            continue
        ab = next((a["id"] for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
        if ab is None:
            continue
        here = (me["pos"]["col"], me["pos"]["row"])
        tiles = [here] + [(t["col"], t["row"]) for t in
                          ((mov_by.get(cid) or {}).get("tiles") or [])[:n_tiles]]
        ctxs = {c: _ctx(rpc, rid, cid, c == "include", predictor)
                for c in ("defaut", "include")}
        for tgt in case["foes"]:
            t = units.get(tgt)
            if t is None or not t.get("alive"):
                continue
            for tile in tiles:
                try:
                    nat = P501.pair_native(rpc, rid, cid, tgt, ab, tile)
                except P501.MontageError:
                    continue                       # paire refusee par le natif -> hors domaine
                vals = {}
                for c, ctx in ctxs.items():
                    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
                    vals[c] = None if cand is None else float(cand["u"])
                rows.append({"regime": regime, "cid": cid, "tgt": tgt, "tile": tile,
                             "ab": ab, "native": nat,
                             "defaut": vals["defaut"], "include": vals["include"]})
    return rows


def _report(rows: list[dict]) -> int:
    """Verdict. Une paire BOUGE si les deux canaux du port different ; le natif ARBITRE le sens."""
    bouge, gain, reg, neutre = [], [], [], []
    for r in rows:
        d, i = r["defaut"], r["include"]
        if d is None or i is None:
            if d is not i:
                bouge.append(r)
                reg.append(r)
            continue
        if abs(i - d) <= EPS:
            continue
        bouge.append(r)
        av, ap = abs(d - r["native"]), abs(i - r["native"])
        (gain if ap < av - EPS else (neutre if abs(ap - av) <= EPS else reg)).append(r)
    print("\n  paires balayees : %d  |  qui BOUGENT a la bascule : %d"
          % (len(rows), len(bouge)))
    print("     -> GAIN (le port se RAPPROCHE du natif)   : %d" % len(gain))
    print("     -> NEUTRE (meme distance au natif)        : %d" % len(neutre))
    print("     -> REGRESSION (le port s'en ECARTE)       : %d" % len(reg))
    for titre, lot in (("GAIN", gain), ("NEUTRE", neutre), ("REGRESSION", reg)):
        for r in lot:
            print("     [%-10s] %-9s u%-3d -> u%-3d @%-8s natif=%12.6f defaut=%12.6f "
                  "include=%12.6f  d=%+.6f"
                  % (titre, r["regime"], r["cid"], r["tgt"], str(r["tile"]), r["native"],
                     -1 if r["defaut"] is None else r["defaut"],
                     -1 if r["include"] is None else r["include"],
                     (0 if (r["defaut"] is None or r["include"] is None)
                      else r["include"] - r["defaut"])))
    # ⚠ CE QUI SUIT N'EST PAS UNE METRIQUE D'AGREEMENT. Le balayage prend des tuiles de MOVE sans
    # verifier que la cible y est a portee : le natif rend alors 0 et l'ecart n'accuse que le
    # harnais. La ligne n'est ici que pour une chose -- ATTESTER que l'ensemble des misses est le
    # MEME sur les deux canaux, donc qu'aucun d'eux n'est attribuable a la bascule.
    def _miss(canal):
        return {(r["regime"], r["cid"], r["tgt"], r["tile"]) for r in rows
                if r[canal] is None or abs(r[canal] - r["native"]) > EPS}

    m0, m1 = _miss("defaut"), _miss("include")
    cle_bouge = {(r["regime"], r["cid"], r["tgt"], r["tile"]) for r in bouge}
    hors = (m0 ^ m1) - cle_bouge
    print("  ecart natif <-> port : %d miss [canal nu] / %d miss [canal de production]" % (len(m0), len(m1)))
    print("     difference des deux ensembles ENTIEREMENT expliquee par les paires qui bougent : %s"
          % ("OUI" if not hors else "NON -- %s" % sorted(hors)))
    print("     (ce n'est PAS un agreement : le balayage prend des tuiles de move sans verifier la")
    print("      portee, et le natif y rend 0. Seul le DEPLACEMENT entre canaux mesure la bascule.)")
    for k in sorted(m1)[:12]:
        r = next(x for x in rows if (x["regime"], x["cid"], x["tgt"], x["tile"]) == k)
        print("     MISS %-9s u%-3d -> u%-3d @%-8s natif=%.6f nu=%s prod=%s"
              % (r["regime"], r["cid"], r["tgt"], str(r["tile"]), r["native"], r["defaut"],
                 r["include"]))
    return len(reg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="41504")
    ap.add_argument("--p-units", default=P_UNITS)
    ap.add_argument("--a-units", default=A_UNITS)
    ap.add_argument("--tiles", type=int, default=2, help="tuiles de move balayees en plus de l'origine")
    ap.add_argument("--stage", choices=("rings", "501"), default="rings",
                    help="`501` = le montage DISCRIMINANT de #501 (caster/cible a distance 3)")
    ap.add_argument("--gap", type=int, default=4, help="distance entre les deux amas (stage rings)")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(args.state_file, args.board, args.seed, args.p_units, args.a_units)
    try:
        if args.stage == "501":
            # Le montage DISCRIMINANT de #501 : caster et cible a DIST=3 (le predicat natif est NIE
            # au contact, donc le terme n'entre QU'A distance).
            c = P501._stage(sid, rpc, rid)
            case = {"rid": rid, "player": c["player"], "mine": [c["cid"]], "foes": [c["tgt"]]}
        else:
            case = _stage(sid, rpc, rid, args.gap)
        print("runner %d | board %s seed %s | stage=%s | %d casters x %d cibles"
              % (rid, args.board, args.seed, args.stage, len(case["mine"]), len(case["foes"])))
        n_a = blast(rpc, rid, "A-actif")
        rows = sweep(rpc, rid, case, args.tiles, "A-actif")
        r = rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120) or {}
        if not r.get("ok"):
            raise MontageError(f"montage NON INSTALLE : endturn refuse -- {r}")
        n_b = blast(rpc, rid, "B-inerte")
        rows += sweep(rpc, rid, case, args.tiles, "B-inerte")
        if n_a == 0 and n_b == 0:
            raise MontageError("montage DEGENERE : le canal n'AJOUTE rien dans aucun des deux "
                               "regimes -- ce balayage ne mesurerait RIEN (vice de `CE3`/#443)")
        return _report(rows)
    finally:
        if not args.keep:
            rpc("disposeRunner", {"runnerId": rid}, 30)


if __name__ == "__main__":
    raise SystemExit(main())
