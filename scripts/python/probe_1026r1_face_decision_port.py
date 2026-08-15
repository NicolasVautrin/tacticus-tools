#!/usr/bin/env python
"""#1026-r1 -- CONFRONTATION du port de la face DECISION de `1026 BasiliskBarrage`.

    python probe_1026r1_face_decision_port.py --arm all

`probe_1026_face_decision_live.py` a mesure le NATIF et leve le verrou (le natif resout bien
l'occupant de chaque tuile d'obus). Ce probe-ci confronte le PORT a ce meme oracle, **PAR TUILE**
-- pas sur un scalaire agrege, parce qu'un accord global peut cacher deux erreurs qui se
compensent (c'est la forme exigee par la fiche, et celle de `probe_302_2::per_tile` pour 1169).

ORACLE : `pairUtility(caster, <tileEntityId>, 1026)` =
`ComparablePlaybook$$CalculateUtilityFromPredictions` sur une cible TUILE, c'est-a-dire le terme
PREDICTION SEUL (ni custom, ni terme `Tile`). Cote port, le meme terme est
`BasiliskBarragePlaybook.make_damage_predictions` -> `calculate_utility_from_predictions`.

LES QUATRE ETAGES
-----------------
    [1] ACCORD PAR TUILE      port vs natif sur CHAQUE tuile eligible, tolerance relative.
    [2] REGIME SEPARANT       le montage doit FAIRE VARIER l'observable, sinon [1] est vacant :
                              on rejoue les deux bras du probe amont (temoin DEPLACE) et on exige
                              un ecart NON NUL sur T1 et EXACTEMENT NUL sur le temoin de controle.
    [3] PAS DE DOUBLON        `_best_attack` presente une cible UNITE ; le playbook doit alors
                              rendre `[]` (sinon 1026 serait comptee DEUX fois -- une par la route
                              non-attaque, une par la route d'attaque). C'est le point que la fiche
                              disait bloquant : on le VERIFIE au lieu de le supposer.
    [4] POIDS DU BATCH        `probability1` doit valoir `numShells / |pool ENTIER|`, denominateur
                              pris AVANT toute resolution d'occupant. Un port qui diviserait par le
                              nombre de tuiles OCCUPEES gonflerait l'utilite des barrages qui
                              tombent surtout a vide -- et [1] seul ne le verrait pas sur un board
                              dense.

TRI-ETAT
--------
    rc 0   VERT   -- les quatre etages passent
    rc 1   ROUGE  -- desaccord, regime degenere, doublon, ou poids faux
    rc 2   PAS MESURE -- montage non installe / oracle muet. JAMAIS rabattu sur un vert.

Discipline runner : `--state-file` ABSOLU sous `logs/`, runner DISPOSE en sortie. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import rl_duel as R                                                            # noqa: E402
import rl_collect_batch as B                                                   # noqa: E402
import probe_1026_face_decision_live as AMONT                                  # noqa: E402

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

ABILITY_1026 = 1026
#: Tolerance RELATIVE de l'accord par tuile. Le natif calcule en `Fix64` (point fixe), le port en
#: `float` : un ecart de dernier bit est attendu, un ecart de structure ne l'est pas.
TOL_REL = 1e-4


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


def _monter(arm: str, seed: int, board: str):
    """Monte le bras `arm` du montage AMONT et rend `(rid, sid, rpc, cid, ctx, ids)`.

    Le montage n'est PAS recopie : il est importe de `probe_1026_face_decision_live`, pour que les
    deux probes ne puissent pas diverger sur la geometrie (le vice que #332 et #390 ont paye)."""
    pos_voisin = AMONT.ARMS[arm]
    sf = str(PYDIR.parents[1] / "logs" / ("probe1026r1_port_%s.json" % arm))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    argv = ["build", "--seed", str(int(seed)), "--board", str(board),
            "--p-units", AMONT.CASTER,
            "--a-units", "%s,%s,%s" % (AMONT.FOE_GROUPE, AMONT.FOE_VOISIN, AMONT.FOE_ISOLE),
            "--place", "%s:%d,%d" % (AMONT.CASTER, AMONT.POS_CASTER[0], AMONT.POS_CASTER[1]),
            "--a-place", "%s:%d,%d" % (AMONT.FOE_GROUPE, AMONT.POS_T1[0], AMONT.POS_T1[1]),
            "--a-place", "%s:%d,%d" % (AMONT.FOE_VOISIN, pos_voisin[0], pos_voisin[1]),
            "--a-place", "%s:%d,%d" % (AMONT.FOE_ISOLE, AMONT.POS_T3[0], AMONT.POS_T3[1]),
            "--state-file", sf]
    if R.main(argv) != 0:
        raise RuntimeError("build ECHOUE : %s" % " ".join(argv))
    rid = json.loads(Path(sf).read_text(encoding="utf-8")).get("runnerId")
    if rid is None:
        raise RuntimeError("build sans runnerId")
    sid = B._resolve_session()

    def rpc(method, body=None, timeout=120):
        return _unwrap(B._rpc(sid, method, [{**(body or {}), "runnerId": rid}],
                              timeout=timeout)) or {}

    dv = rpc("decisionView", {"maxRank": 32, "allAbilities": True}, 180)
    ids = {u.get("visualId"): int(u["id"]) for u in (dv.get("units") or []) if u.get("alive")}
    for k in (AMONT.CASTER, AMONT.FOE_GROUPE, AMONT.FOE_VOISIN, AMONT.FOE_ISOLE):
        if k not in ids:
            raise RuntimeError("montage NON INSTALLE : %s absent (%s)" % (k, sorted(ids)))
    cid = ids[AMONT.CASTER]

    from engine import weights as W
    from engine.ai import context as AICTX
    from engine.playbook import scene as _scene

    def _seam(method, body, timeout=90):
        return _unwrap(B._rpc(sid, method, [body], timeout=timeout)) or {}

    mov = rpc("aiMovableTiles", {}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(_seam, rid)
    ctx = AICTX.build(_seam, rid, dv, mov_by_unit, cid, W.load(), predictor)
    return rid, sid, rpc, cid, ctx, ids


def _par_tuile(rpc, cid, ctx) -> list:
    """`[{tile, pos, nev, port, nat, err}]` -- l'accord ETAGE par ETAGE."""
    import engine.playbook as PB

    pb = PB.REGISTRY[ABILITY_1026]
    pos_by_tid = {t: p for p, t in (ctx.tile_id_by_pos or {}).items()}
    rows = []
    for tid in pb.eligible_targets(ctx, ABILITY_1026):
        evs = pb.make_damage_predictions(ctx, ctx.origin, tid, ABILITY_1026) or []
        port = (pb.calculate_utility_from_predictions(ctx, ctx.origin, tid, ABILITY_1026, evs)[0]
                if evs else 0.0)
        r = rpc("pairUtility", {"unitId": cid, "targetId": int(tid),
                                "abilityType": ABILITY_1026}, 120)
        rows.append({"tile": int(tid), "pos": pos_by_tid.get(tid), "nev": len(evs),
                     "port": float(port), "nat": r.get("utility"), "err": r.get("error"),
                     "probs": sorted({round(e.probability1, 6) for e in evs})})
    return rows


def _ecart_relatif(a: float, b: float) -> float:
    d = abs(a - b)
    m = max(abs(a), abs(b), 1.0)
    return d / m


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=sorted(AMONT.ARMS) + ["all"], default="all")
    ap.add_argument("--seed", type=int, default=AMONT.SEED)
    ap.add_argument("--board", default=AMONT.BOARD)
    a = ap.parse_args(argv)
    arms = sorted(AMONT.ARMS) if a.arm == "all" else [a.arm]

    print("[1026-r1] confrontation de la face DECISION -- board=%s seed=%d" % (a.board, a.seed))
    res, fautes, rids = {}, [], []
    try:
        for arm in arms:
            rid, _sid, rpc, cid, ctx, ids = _monter(arm, a.seed, a.board)
            rids.append(rid)
            tid_by_pos = dict(ctx.tile_id_by_pos or {})
            rows = _par_tuile(rpc, cid, ctx)
            res[arm] = {"rows": rows, "ctx": ctx, "cid": cid, "ids": ids,
                        "tileT1": tid_by_pos.get(AMONT.POS_T1),
                        "tileT3": tid_by_pos.get(AMONT.POS_T3)}

            print("\n=== bras %s (temoin @%s) -- %d tuile(s) eligible(s) ==="
                  % (arm, AMONT.ARMS[arm], len(rows)))
            muets = [r for r in rows if r["err"] or r["nat"] is None]
            if muets:
                print("  ORACLE MUET sur %d tuile(s) -- PAS MESURE." % len(muets))
                for r in muets[:4]:
                    print("     tile=%s pos=%s err=%s" % (r["tile"], r["pos"], r["err"]))
                return EX_PAS_MESURE
            if not rows:
                print("  AUCUNE tuile eligible -- le montage ne mesure rien. PAS MESURE.")
                return EX_PAS_MESURE
            for r in sorted(rows, key=lambda x: -float(x["nat"] or 0.0))[:10]:
                e = _ecart_relatif(r["port"], float(r["nat"]))
                marque = "" if e <= TOL_REL else "   *** ECART ***"
                print("    tile=%-4s pos=%-8s nev=%-3d port=%12.6f  nat=%12.6f  rel=%.2e%s"
                      % (r["tile"], r["pos"], r["nev"], r["port"], float(r["nat"]), e, marque))
            hors = [r for r in rows if _ecart_relatif(r["port"], float(r["nat"])) > TOL_REL]
            print("  [1] ACCORD PAR TUILE : %d/%d dans la tolerance %.0e"
                  % (len(rows) - len(hors), len(rows), TOL_REL))
            if hors:
                fautes.append("[1] bras %s : %d tuile(s) hors tolerance" % (arm, len(hors)))

        # [2] LE MONTAGE SEPARE-T-IL ? Sans ce cran, [1] pourrait passer sur un regime ou l'on
        #     compare 0 a 0 -- un accord en regime DEGENERE ne prouve rien.
        if len(arms) == 2:
            def _nat(arm, tid):
                return next((float(r["nat"]) for r in res[arm]["rows"] if r["tile"] == tid), None)

            def _port(arm, tid):
                return next((r["port"] for r in res[arm]["rows"] if r["tile"] == tid), None)

            t1v, t1i = res["voisin"]["tileT1"], res["isole"]["tileT1"]
            t3v, t3i = res["voisin"]["tileT3"], res["isole"]["tileT3"]
            print("\n=== [2] REGIME SEPARANT ===")
            for nom, cv, ci in (("T1 (une tuile ring-1 change d'occupation)", t1v, t1i),
                                ("T3 (temoin de CONTROLE, rien ne change)", t3v, t3i)):
                nv, ni = _nat("voisin", cv), _nat("isole", ci)
                pv, pi = _port("voisin", cv), _port("isole", ci)
                if None in (nv, ni, pv, pi):
                    print("  %s : NON MESURE" % nom)
                    return EX_PAS_MESURE
                print("  %-46s natif %+12.6f   port %+12.6f" % (nom, nv - ni, pv - pi))
            dn = _nat("voisin", t1v) - _nat("isole", t1i)
            dp = _port("voisin", t1v) - _port("isole", t1i)
            c_n = _nat("voisin", t3v) - _nat("isole", t3i)
            c_p = _port("voisin", t3v) - _port("isole", t3i)
            if abs(dn) < 1e-6:
                fautes.append("[2] le montage NE SEPARE PAS cote natif (ecart T1 nul) -- "
                              "l'accord de [1] serait vacant")
            if abs(dp) < 1e-6:
                fautes.append("[2] le port NE BOUGE PAS alors que le natif bouge de %+.6f" % dn)
            if abs(c_n) > 1e-9 or abs(c_p) > 1e-9:
                fautes.append("[2] le TEMOIN DE CONTROLE bouge (natif %+.9f, port %+.9f) -- "
                              "le montage fait varier autre chose que l'occupation" % (c_n, c_p))

        # [3] PAS DE DOUBLON -- une cible UNITE doit rendre AUCUN event.
        print("\n=== [3] PAS DE DOUBLON avec la route d'attaque ===")
        import engine.playbook as PB
        import engine.ai.state_bridge as SB
        pb = PB.REGISTRY[ABILITY_1026]
        arm0 = arms[0]
        ctx0, ids0 = res[arm0]["ctx"], res[arm0]["ids"]
        vis = SB._attack_abilities(AMONT.CASTER)
        print("  `_attack_abilities(%s)` = %s" % (AMONT.CASTER, vis))
        print("  -> 1026 y est %s : la route d'attaque la PRESENTE, comme pour 1169 et 1148."
              % ("PRESENTE" if any(x == ABILITY_1026 for x, _ in vis) else "ABSENTE"))
        for nom in (AMONT.FOE_GROUPE, AMONT.FOE_ISOLE):
            uid = ids0.get(nom)
            evs = pb.make_damage_predictions(ctx0, ctx0.origin, uid, ABILITY_1026) or []
            print("     cible UNITE %-20s (id=%s) -> %d event(s)" % (nom, uid, len(evs)))
            if evs:
                fautes.append("[3] cible UNITE %s rend %d event(s) : DOUBLON avec _best_attack"
                              % (nom, len(evs)))
        print("  (une liste vide -> `calculate_action_utility` rend `None` -> aucune action)")

        # [4] LE POIDS DU BATCH -- denominateur = pool ENTIER.
        #: Le bras est NOMME : [4] porte sur `arms[0]`, alors que le tableau par tuile ci-dessus a
        #: imprime les DEUX bras. Sans ce rappel, un lecteur compare le compte d'occupants de [4] au
        #: `nev` de l'autre bras et croit a une incoherence (les deux bras different justement par
        #: l'occupation d'une tuile de l'anneau 1).
        print("\n=== [4] POIDS DU BATCH (`probability1` = numShells / |pool ENTIER|) "
              "-- bras `%s` ===" % arm0)
        from engine.runner.abilities.astramilitarum import (basilisk_num_shells_from_turns,
                                                            basilisk_tiles_at_distance_on_board)
        sc = ctx0.scene
        turns = sc.turns_started(ctx0.uid)
        g, mb, ms, tot = basilisk_num_shells_from_turns(turns)
        t1 = res[arm0]["tileT1"]
        tp = sc.board.coord(t1)
        p_miss = basilisk_tiles_at_distance_on_board(sc.board, tp, 2)
        p_maybe = [t1] + basilisk_tiles_at_distance_on_board(sc.board, tp, 1)
        #: ⚠ LE CRITERE EST L'INCLUSION, PAS L'EGALITE -- et une premiere ecriture exigeait
        #: l'egalite, ce qui l'a fait rougir sur un port JUSTE. Un groupe dont AUCUNE tuile n'est
        #: occupee ne produit legitimement aucun event, donc son poids n'apparait pas : sur ce
        #: montage l'anneau 2 de T1 est vide, et `2/12` est absent a bon droit. Ce qui serait une
        #: faute, c'est un poids HORS des attendus -- typiquement `numShells / <tuiles OCCUPEES>`
        #: (ici `3/2 = 1.5` au lieu de `3/7`), et l'inclusion le voit.
        #: L'occupation se compte par LE MEME noeud DSL que le port (`Units(FixedTileIds([...]))`),
        #: jamais par une comparaison de positions recodee ici : une premiere ecriture comparait
        #: `u["pos"]` a `board.coord(tid)` et rendait `0` partout alors que deux events sortaient --
        #: un chiffre FAUX dans un diagnostic est pire qu'un chiffre absent.
        from engine.entities.selectors import Units as _Units
        from engine.entities.selectors.accessors import FixedTileIds as _FTI
        from engine.playbook.tile_targets import dsl_context_for_tile_target as _dctx_for
        _d = _dctx_for(ctx0)

        def _occupants(pool):
            if _d is None:
                return None                      # NON MESURE, jamais un zero
            return sum(1 for tid in pool if (_Units(_FTI([int(tid)])).select(_d) or []))

        attendus, detail = set(), []
        for nom, n, pool in (("miss", ms, p_miss), ("maybe", mb, p_maybe), ("guar", g, [t1])):
            if int(n) >= 1 and pool:
                r = round(float(n) / float(len(pool)), 6)
                attendus.add(r)
                nocc = _occupants(pool)
                detail.append("%s: %d/%d = %.6f  (tuiles OCCUPEES : %s)"
                              % (nom, int(n), len(pool), r,
                                 "NON MESURE" if nocc is None else nocc))
        vus = {p for r in res[arm0]["rows"] if r["tile"] == t1 for p in r["probs"]}
        print("  turns_started=%s -> (guar=%d, maybe=%d, miss=%d, total=%d)" % (turns, g, mb, ms, tot))
        for d in detail:
            print("     %s" % d)
        print("  probability1 ATTENDUS=%s   VUS=%s" % (sorted(attendus), sorted(vus)))
        hors = sorted(vus - attendus)
        if hors:
            fautes.append("[4] poids HORS des attendus : %s (attendus %s) -- le denominateur "
                          "n'est pas le pool ENTIER" % (hors, sorted(attendus)))
        if not vus:
            fautes.append("[4] AUCUN poids observe : l'etage ne mesure rien (regime degenere)")
    except RuntimeError as exc:
        print("  PAS MESURE : %s" % exc)
        return EX_PAS_MESURE
    finally:
        for rid in rids:
            try:
                B._rpc(B._resolve_session(), "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:
                pass

    print()
    for f in fautes:
        print("FAUTE : %s" % f)
    if fautes:
        print("\n[1026-r1] rc=%d -- ROUGE (%d faute(s))." % (EX_ROUGE, len(fautes)))
        return EX_ROUGE
    print("[1026-r1] rc=%d -- VERT : accord par tuile, regime separant, aucun doublon, "
          "poids exact." % EX_VERT)
    return EX_VERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
