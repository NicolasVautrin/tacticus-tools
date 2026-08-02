"""#419-r1-tr9-r4 -- DECOMPOSITION PAR ETAGE de l'ecart de PREDICTION sur l'attaque normale
CONCRETE `1128 Boltstorm_NormalAttack` (`templAggressor`).

Le releve de #419-r1-tr9 (regime `foreign`) donnait, contre `necroWarden` :

    port  [1762, 2642]
    natif [ 876, 1314]

soit un rapport ~2.01 sur les DEUX bornes -- alors que contre `astraBullgryn` le meme montage
rendait `port [2628, 3942]` / `natif [2631, 3945]`, soit 3 points. L'ecart n'est donc PAS un
doublement structurel du fold (il serait present sur toutes les cibles) : il est PAR CIBLE.

Ce probe ne fitte AUCUN scalaire. Il decompose la prediction en ses DEUX etages natifs
(`IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$PredictAttack` =
`ALoki_NormalAttackAbility$$PredictAttack` + `GetAdditionalDamagePrediction`, sommes par
`IdunBattle.Core.Services.DamagePredictionResult$$Add`) et mesure CHAQUE etage des deux cotes :

    ETAGE 1 -- BASE : bras APPARIE `--unit-stat templAggressor:PassiveAbilities=[]` (l'attaque
              normale retombe a la generique 69, aucun fold natif) contre le port avec le registre
              `_RANGED_FOLLOWUP_PASSIVES` VIDE. Meme board, meme seed, meme placement, memes stats
              -- appariement par `visualId`.
    ETAGE 2 -- FOLD : `total - base`, des deux cotes. `DamagePredictionResult$$Add` etant une somme
              champ a champ, la soustraction est EXACTE cote natif.

C'est ce qui separe « le port ajoute un fold que le natif n'ajoute pas » de « le port se trompe de
base » -- et, dans ce dernier cas, quel champ (`appliedHits`, bornes, armure) porte l'ecart.

Usage :
    python scripts/python/probe_419r1tr9_r4_boltstorm_pred.py --state-file <chemin ABSOLU>
        [--foes necroWarden,astraBullgryn,tauAunShi] [--mutants]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419r1tr9_r4_boltstorm_pred_live.py`.
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
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402

BOARD = "MC1_67"
SEED = "41904"
CASTER = "templAggressor"          # HERO au pool ; `Boltstorm` (1090) est son SEUL passif, et son
                                   # attaque normale CONCRETE est `1128 Boltstorm_NormalAttack`.
DEFAULT_FOES = "necroWarden,astraBullgryn,tauAunShi"
HP = 40000                         # personne ne meurt : `Health` ET `RemainingHealth` (#438)
EPS = 1e-6


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- montage

def build_args(foes: str, arm: str = "kit") -> list:
    """Arguments `rl_duel build` du bras demande, SANS `--seed` ni `--state-file`.

    `kit`  : le kit d'origine -- `Boltstorm` monte, attaque normale concrete `1128`.
    `base` : MEME bataille, `templAggressor:PassiveAbilities=[]` -- l'attaque normale retombe a la
             generique `69` et le natif ne folde plus. C'est le bras qui rend la BASE NATIVE
             mesurable (protocole de #446-r1 SS4)."""
    stats = ";".join(f"{v}:Health={HP},RemainingHealth={HP}"
                     for v in (CASTER,) + tuple(foes.split(",")))
    if arm == "base":
        stats += f";{CASTER}:PassiveAbilities=[]"
    return ["--board", BOARD, "--p-units", CASTER, "--a-units", foes, "--unit-stat", stats]


def _build(state_file: str, foes: str, arm: str = "kit") -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            *build_args(foes, arm), "--state-file", state_file]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def _normal_ability_id(rpc, rid, uid) -> int:
    """L'`ActiveAbilityType` CONCRET de l'attaque normale de `uid` (`abilityTargets`, `kind ==
    normal`) -- `1128` avec le passif, `69` sans lui."""
    r = rpc("abilityTargets", {"runnerId": rid, "unitId": uid}, 60) or {}
    for u in (r.get("units") or ()):
        if u.get("unitId") != uid:
            continue
        for a in (u.get("abilities") or ()):
            if a.get("kind") == "normal":
                return int(a.get("abilityId"))
    raise MontageError(f"u{uid} n'a pas d'attaque normale au canal abilityTargets")


def _find_layout(cells, elev, walk, n_foes: int):
    """`(C, [E1..En])` : une tuile de caster a >= 3 voisins de mouvement, et `n_foes` tuiles
    d'ennemi a distance EXACTEMENT 2 de `C` -- jamais adjacentes (l'adjacence basculerait l'arme en
    MELEE et changerait le regime), mutuellement non adjacentes (l'aura `BigTarget` d'`astraBullgryn`
    retire un coup RANGED a ses voisins : deux cibles adjacentes melangeraient les regimes), toutes a
    la MEME elevation que `C` (le bonus d'elevation x1.5 ne doit pas varier d'une cible a l'autre).
    """
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for c in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        if len(P124._move_ring(c, walk, elev)) < 3:
            continue
        near = [q for q in cells if q != c and hexgeo.distance(c, q) == 2
                and elev.get(q) == elev.get(c) and P124._gated_path(c, q, walk, elev)]
        picked = []
        for q in near:
            if all(hexgeo.distance(q, r) >= 2 for r in picked):
                picked.append(q)
            if len(picked) == n_foes:
                return c, picked
    return None, None


def build_case(sid, rpc, rid: int, foes: str, drive: bool = True) -> dict:
    elev, walk, _tid = P124._board(sid, rid)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    dv, _pos = P124._positions(sid, rid)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    cid, myplayer = mine[0]["id"], mine[0]["owner"]
    want_vis = tuple(foes.split(","))
    vis_uid = {}
    for vis in want_vis:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        vis_uid[vis] = u["id"]

    if drive:
        C, EP = _find_layout(cells, elev, walk, len(want_vis))
        if C is None:
            raise MontageError(f"montage NON INSTALLE : aucune geometrie (caster a 3 voisins + "
                               f"{len(want_vis)} tuiles a distance 2, meme elevation) sur {BOARD}")
        want = {cid: C}
        want.update({vis_uid[v]: p for v, p in zip(want_vis, EP)})
        if not P124._drive_to(sid, rid, walk, elev, want):
            _dv, pos = P124._positions(sid, rid)
            raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {want}, "
                               f"obtenu { {u: pos.get(u) for u in want} }")
        P124._give_turn_back(sid, rid, myplayer)
    else:
        # INSPECTION d'un runner deja place (ex. celui d'un AUTRE probe) : on prend les positions
        # telles quelles. Aucun drive, donc aucune hypothese de geometrie -- c'est l'appelant qui
        # sait ce qu'il a monte.
        C = _pos.get(cid)
        want = {cid: C}
        want.update({vis_uid[v]: _pos.get(vis_uid[v]) for v in want_vis})
    dv, ctx = _fresh_ctx(rpc, rid, cid)
    if ctx.origin != C:
        raise MontageError(f"montage NON INSTALLE : le caster est en {ctx.origin}, voulu {C}")
    ab = _normal_ability_id(rpc, rid, cid)
    return {"rid": rid, "cid": cid, "C": C, "ab": ab, "ctx": ctx, "elev": elev, "walk": walk,
            "myplayer": myplayer, "vis_uid": vis_uid, "want": want, "foes": want_vis}


# --------------------------------------------------------------------------- oracles

def native_fields(rpc, rid, cid, tgt, ab, tile) -> dict:
    """`aiPlaybookPredict` -- le `DamagePredictionResult` que le NATIF construit pour la paire,
    depuis `tile`. C'est l'oracle de DECISION (celui que `pairUtility` consomme)."""
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                                  "abilityType": ab, "col": tile[0], "row": tile[1]}, 60) or {}
    if not r.get("ok"):
        raise MontageError(f"aiPlaybookPredict indisponible pour {tile} / cible {tgt}: {r}")
    evs = r.get("events") or []
    ev = next((e for e in evs if e.get("targetId") == tgt), evs[0] if evs else None)
    if ev is None:
        raise MontageError(f"aiPlaybookPredict n'a rendu AUCUN event pour la cible {tgt}")
    return {"rawMin": ev.get("willKillDmg") or 0, "rawMax": ev.get("mightKillDmg") or 0,
            "hits": ev.get("appliedHits") or 0,
            "hpBefore": ev.get("hpBefore") or 0, "shieldBefore": ev.get("shieldBefore") or 0,
            "healthMin": ev.get("healthDmgMin") or 0, "healthMax": ev.get("healthDmgMax") or 0}


def port_fields(scene, cid, tgt, tile, *, fold: bool = True) -> dict:
    """Le port. `fold=False` vide le registre `_RANGED_FOLLOWUP_PASSIVES` -> la BASE seule
    (`ALoki_NormalAttackAbility$$PredictAttack`), qui est l'etage 1 du mold natif."""
    import engine.playbook.prediction.normal_attack as NA
    from engine.playbook.prediction import make_normal_attack_predictions
    saved = NA._RANGED_FOLLOWUP_PASSIVES
    if not fold:
        NA._RANGED_FOLLOWUP_PASSIVES = ()
    try:
        ev, meta = make_normal_attack_predictions(scene, cid, tgt, tile, meta=True)
    finally:
        NA._RANGED_FOLLOWUP_PASSIVES = saved
    p = ev.prediction
    f = ev.composite_fields()
    return {"rawMin": p.raw_health_damage.min, "rawMax": p.raw_health_damage.max,
            "hits": p.applied_hits,
            "hpBefore": f.get("hpBefore"), "shieldBefore": f.get("shieldBefore"),
            "healthMin": f.get("healthDmgMin"), "healthMax": f.get("healthDmgMax"),
            "meta": meta}


def _sub(a: dict, b: dict) -> dict:
    """`a - b` sur les champs sommes par `DamagePredictionResult$$Add` (le fold est une SOMME)."""
    return {k: (a.get(k) or 0) - (b.get(k) or 0) for k in ("rawMin", "rawMax", "hits")}


# --------------------------------------------------------------------------- mesure

def target_context(case: dict, uid: int) -> dict:
    """Le CONTEXTE GEOMETRIQUE de la paire, tel que le port le lit -- ce qui decide l'arme (donc la
    gate `!IsMelee` du mold), le compte de coups d'arme et le bonus d'elevation. Sans ces champs, un
    ecart de coups se lit comme un mystere ; avec eux il se rattache a une lecture."""
    from engine.playbook.prediction._shared import _weapon_pierce
    from engine.services.battle_query import are_tiles_adjacent
    ctx, tile = case["ctx"], case["C"]
    sc = ctx.scene
    t_pos = sc.pos(uid)
    adj = are_tiles_adjacent(tile, t_pos, sc.board)
    dist = hexgeo.distance(tile, t_pos) if (tile and t_pos) else None
    pierce, ranged, whits, prof = _weapon_pierce(sc, case["cid"], adj, dist)
    return {"pos": t_pos, "dist": dist, "adjacent": adj,
            "elev_caster": case["elev"].get(tuple(tile)),
            "elev_target": case["elev"].get(tuple(t_pos)) if t_pos else None,
            "terrain": (sc.board.terrain_at(t_pos[0], t_pos[1])
                        if (sc.board is not None and t_pos) else None),
            "weapon": {"pierce": pierce, "ranged": ranged, "hits": whits, "profile": prof},
            "tgt_effects": [e.name for e in (sc.effects(uid) or [])] or None,
            "tile_effects": sorted((sc.tile_effects_by_pos or {}).get(tuple(t_pos)) or ()) or None}


def measure(rpc, case: dict) -> list:
    """Une ligne par cible : natif TOTAL, port TOTAL, port BASE (registre vide), port FOLD."""
    out = []
    ctx, tile, ab, cid = case["ctx"], case["C"], case["ab"], case["cid"]
    for vis in case["foes"]:
        uid = case["vis_uid"][vis]
        nat = native_fields(rpc, case["rid"], cid, uid, ab, tile)
        prt = port_fields(ctx.scene, cid, uid, tile, fold=True)
        prt_base = port_fields(ctx.scene, cid, uid, tile, fold=False)
        out.append({"vis": vis, "uid": uid, "native": nat, "port": prt,
                    "port_base": prt_base, "port_fold": _sub(prt, prt_base),
                    "ctx": target_context(case, uid),
                    "armor": ctx.scene.armor(uid), "shield": ctx.scene.shield(uid),
                    "hpmax": ctx.hpmax_by_id.get(uid)})
    return out


def native_baseline(sid, rpc, case: dict, foes: str, make_rid, dispose=None) -> dict:
    """BRAS APPARIE : re-monte la MEME bataille avec `templAggressor:PassiveAbilities=[]`, y rejoue
    le MEME placement (apparie par `visualId`) et rend la prediction NATIVE de chaque cible.

    `fold_natif = total_natif - base_natif` devient une difference de deux mesures NATIVES : le port
    n'entre pas dans sa definition. Le runner du bras est DISPOSE des la mesure faite."""
    rid = make_rid()
    try:
        elev, walk, _tid = P124._board(sid, rid)
        dv, _pos = P124._positions(sid, rid)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        mine = [u for u in units if u.get("ctrl")]
        if not mine:
            raise MontageError("bras BASE : aucune unite controlee")
        cid2, myplayer2 = mine[0]["id"], mine[0]["owner"]
        vis_uid2 = {}
        for vis in case["foes"]:
            u = next((x for x in units if x.get("owner") != myplayer2 and x.get("alive")
                      and x.get("visualId") == vis), None)
            if u is None:
                raise MontageError(f"bras BASE : {vis} absent du roster adverse")
            vis_uid2[vis] = u["id"]
        want = {cid2: case["C"]}
        want.update({vis_uid2[v]: case["want"][case["vis_uid"][v]] for v in case["foes"]})
        if not P124._drive_to(sid, rid, walk, elev, want):
            raise MontageError(f"bras BASE : placement incomplet -- voulu {want}")
        P124._give_turn_back(sid, rid, myplayer2)
        ab2 = _normal_ability_id(rpc, rid, cid2)
        if ab2 == case["ab"]:
            raise MontageError(f"bras BASE NON INSTALLE : l'attaque normale y vaut encore "
                               f"{ab2} -- `PassiveAbilities=[]` n'a pas retire `Boltstorm`")
        out = {"ab": ab2}
        for vis in case["foes"]:
            out[vis] = native_fields(rpc, rid, cid2, vis_uid2[vis], ab2, case["C"])
        return out
    finally:
        if dispose is not None:
            dispose(rid)


def mutants(case: dict, rows: list) -> list:
    """CONTRE-EPREUVES. Critere = DEPLACEMENT du port par rapport au port NON MUTE, jamais l'ecart
    au natif (la paire porte des residus hors-perimetre : `abs(port - natif) > EPS` serait vrai
    meme pour un mutant inerte).

      `no_fold`     -- registre `_RANGED_FOLLOWUP_PASSIVES` vide : plus aucun fold.
      `fold_twice`  -- le fold ajoute DEUX fois (l'hypothese « etage compte deux fois »).
      `amount_min`  -- montant du fold = `minDmg` seul (l'ancienne lecture « slot 4 = MIN »)."""
    import engine.playbook.prediction.normal_attack as NA
    ctx, tile, cid = case["ctx"], case["C"], case["cid"]
    ref = {r["vis"]: (r["port"]["rawMin"], r["port"]["rawMax"], r["port"]["hits"]) for r in rows}
    out = []
    for name in ("no_fold", "fold_twice", "amount_min"):
        saved_reg = NA._RANGED_FOLLOWUP_PASSIVES
        saved_avg = NA.calculate_average
        try:
            if name == "no_fold":
                NA._RANGED_FOLLOWUP_PASSIVES = ()
            elif name == "fold_twice":
                NA._RANGED_FOLLOWUP_PASSIVES = ("Boltstorm", "Boltstorm")
            elif name == "amount_min":
                NA.calculate_average = lambda mn, mx: int(mn)
            got = {}
            for r in rows:
                f = port_fields(ctx.scene, cid, r["uid"], tile, fold=True)
                got[r["vis"]] = (f["rawMin"], f["rawMax"], f["hits"])
        finally:
            NA._RANGED_FOLLOWUP_PASSIVES = saved_reg
            NA.calculate_average = saved_avg
        shift = {v: tuple(got[v][i] - ref[v][i] for i in range(3)) for v in ref}
        out.append({"mutant": name, "shift": shift,
                    "bites": any(any(x != 0 for x in s) for s in shift.values())})
    return out


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--foes", default=DEFAULT_FOES)
    ap.add_argument("--runner", type=int, default=None, help="reutilise un runner deja monte")
    ap.add_argument("--no-baseline", action="store_true",
                    help="saute le bras apparie (ne monte qu'UN runner)")
    ap.add_argument("--no-drive", action="store_true",
                    help="INSPECTE un runner deja place (avec --runner) sans rien deplacer")
    ap.add_argument("--mutants", action="store_true", help="joue les contre-epreuves")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = args.runner if args.runner else _build(args.state_file, args.foes, "kit")
    case = build_case(sid, rpc, rid, args.foes, drive=not args.no_drive)
    print(f"runner {rid} | caster u{case['cid']} @ {case['C']} | attaque normale = {case['ab']}")
    rows = measure(rpc, case)

    base = None
    if not args.no_baseline:
        base_state = os.path.splitext(args.state_file)[0] + "_base.json"

        def _make_base():
            return _build(base_state, args.foes, "base")

        def _dispose(_rid):
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", base_state],
                           cwd=_HERE, capture_output=True, text=True)

        base = native_baseline(sid, rpc, case, args.foes, _make_base, _dispose)
        print(f"  bras BASE : attaque normale = {base['ab']} (le fold natif y est ABSENT)")

    for r in rows:
        n, p, pb, pf = r["native"], r["port"], r["port_base"], r["port_fold"]
        print(f"  [{r['vis']:<15}] u{r['uid']} armor={r['armor']} shield={r['shield']} "
              f"hpmax={r['hpmax']}")
        print(f"      TOTAL  nat=({n['rawMin']}, {n['rawMax']}, h{n['hits']})   "
              f"port=({p['rawMin']}, {p['rawMax']}, h{p['hits']})   "
              f"ratio={(p['rawMin'] / n['rawMin']) if n['rawMin'] else float('nan'):.4f}/"
              f"{(p['rawMax'] / n['rawMax']) if n['rawMax'] else float('nan'):.4f}")
        if base is not None:
            nb = base[r["vis"]]
            nf = _sub(n, nb)
            print(f"      BASE   nat=({nb['rawMin']}, {nb['rawMax']}, h{nb['hits']})   "
                  f"port=({pb['rawMin']}, {pb['rawMax']}, h{pb['hits']})   "
                  f"d_base=({pb['rawMin'] - nb['rawMin']:+d}, {pb['rawMax'] - nb['rawMax']:+d}, "
                  f"h{pb['hits'] - nb['hits']:+d})")
            print(f"      FOLD   nat=({nf['rawMin']}, {nf['rawMax']}, h{nf['hits']})   "
                  f"port=({pf['rawMin']}, {pf['rawMax']}, h{pf['hits']})   "
                  f"d_fold=({pf['rawMin'] - nf['rawMin']:+d}, {pf['rawMax'] - nf['rawMax']:+d}, "
                  f"h{pf['hits'] - nf['hits']:+d})")
        else:
            print(f"      BASE   port=({pb['rawMin']}, {pb['rawMax']}, h{pb['hits']})   "
                  f"FOLD port=({pf['rawMin']}, {pf['rawMax']}, h{pf['hits']})")
        m = p.get("meta") or {}
        mb = pb.get("meta") or {}
        print(f"      meta port : base={mb.get('base')} hits={mb.get('hits')} "
              f"pierce={mb.get('pierce')} armor={mb.get('armor')} mods={mb.get('mods')} "
              f"mods_detail={mb.get('mods_detail')} followup={m.get('followup')}")
        c = r["ctx"]
        print(f"      ctx : pos={c['pos']} dist={c['dist']} adj={c['adjacent']} "
              f"elev={c['elev_caster']}->{c['elev_target']} terrain={c['terrain']} "
              f"weapon={c['weapon']} tgt_effects={c['tgt_effects']} tiles={c['tile_effects']}")
    if args.mutants:
        for mu in mutants(case, rows):
            det = " ".join(f"{k}:{v}" for k, v in sorted(mu["shift"].items()))
            print(f"  [mutant {mu['mutant']:<11}] deplacement du port [{det}] "
                  f"({'MORD' if mu['bites'] else 'NE MORD PAS'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
