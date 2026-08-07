#!/usr/bin/env python
"""Probe #523 -- confront LIVE de `1227 HeavyWarpFlamer` (`thousSekhetar` « Sekhetar Robot »,
Thousand Sons), face EXECUTION.

L'ability etait absente d'`ABILITY_CLASSES` : le cast tombait sur le no-op SILENCIEUX de
`AbilityHandler.visit_ActiveAbilityMessage` (`ported: False`, 0 degat, 0 effet, aucune erreur).

GATE DE CONFRONTABILITE : le porteur est un HERO `lineup` ABSENT du seed BC partage (unite ajoutee
par le build `rnca9r7q6c`) -> il entre en bataille par `catalog_inject.write_augmented_seed_bc` +
`rl_duel build --seed-bc` (`docs/rl/case-92-catalog-injection.md` §6), la MEME voie qui a servi a la
face DECISION (#27). Aucun `data/unspawnable_rank*.json` n'existe : rien ne le refuse.

MONTAGE -- LA GEOMETRIE EST FABRIQUEE (`--place` / `--a-place`), PAS SUBIE. L'ensemble de report
natif est `And(Damageable(AdjacentFriends(TARGET)), SurroundingEnemies(CASTER, range))` : il faut
donc quatre positions qui SEPARENT les deux volets, sinon le verdict ne prouve rien. Sur `MC1_67`
(7x9, tout jouable) :

    C = caster (0,0)                                       -- ADJACENT A AUCUN ennemi, sinon
                                                              `ForceMeleeTarget` rabat la portee a 1
    T = cible   (0,2)   d(C,T) = 2 = range                 -- cible du message
    B = (1,2)   adjacent a T, d(C,B) = 2                   -> ELIGIBLE au report
    D = (0,3)   adjacent a T, d(C,D) = 3                   -> EXCLU par `SurroundingEnemies(C, 2)`
    E = (2,0)   d(C,E) = 2, NON adjacent a T               -> EXCLU par `AdjacentFriends(T)`

`D` et `E` sont les deux CONTRE-EXEMPLES : chacun tomberait dans la chaine si l'un des deux volets
manquait au port. Une chaine `[T, B]` est donc un verdict, pas une coincidence.

CE QUI EST CONFRONTE, etage par etage (jamais un scalaire agrege) :
  1. `ported is True`             -- la face EXECUTION n'est plus un no-op ;
  2. la CHAINE                    -- la LISTE ORDONNEE des cibles frappees, offline vs live, ET son
                                     accord avec l'ensemble geometrique attendu {T, B} ;
  3. les degats PAR COUP          -- offline vs live, PAR CIBLE, coup par coup (`Amount` des events
                                     portant `Active_Ability_Type == 1227`) ;
  4. `GetNumTotalHits`            -- `nrOfHits + min(compteur, maxNrOfHits - nrOfHits)` ; le compteur
                                     persistant `(1227, "PSYCHIC_ATTACKS_KEY")` n'est ecrit que par
                                     la triggered 1546, non portee -> il vaut 0 et le total vaut
                                     `nrOfHits`. Confronte au nb de coups LIVE sur la cible ;
  5. le nombre de coups reportes  -- `max(0, H - k - 1) + extraHits(=0)` de `GetLeftOverHits`.

ASCII only (cp1252). Usage :
    python probe_523_heavy_warp_flamer.py [--seed 4242] [--board MC1_67] [--hp-target 900]
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import catalog_inject                                                            # noqa: E402
import hexgeo                                                                    # noqa: E402
from probe_116_necrons import (_alive_units, _build, _capture, _cast_live,       # noqa: E402
                               _dispose, _from_here, _live_per_hit, _offline_cast,
                               _r, _tid, _unit_of)
from rl_collect_batch import _resolve_session                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                # noqa: E402

ROOT = PYDIR.parents[1]
HEAVY_WARP_FLAMER = int(ActiveAbilityType.HeavyWarpFlamer)                       # 1227
CARRIER = "thousSekhetar"

# Positions du montage, cf. l'en-tete. L'ordre de `--a-units` fixe l'appariement avec `--a-place`.
POS_CASTER = (0, 0)
# Les QUATRE tuiles du montage, dans l'ordre T (cible) / B (relais) / D (hors portee) / E (hors
# adjacence). Les `visualId` qui les occupent sont pilotables par `--foes` : le nombre de coups
# REELLEMENT appliques depend de la cible (`AttackHitsWithModifiersFormula`), et c'est lui qui decide
# si `max(0, H - k - 1)` peut etre > 0.
POS_FOES = [(0, 2), (1, 2), (0, 3), (2, 0)]
FOES_DEFAULT = "eldarRanger,astraBullgryn,tauCrisis,necroWarden"


def _fmt_chain(chain):
    """`[cible: coups_demandes -> coups_appliques (total)]` par maillon."""
    return " | ".join("u%s: hits=%s applied=%s total=%s"
                      % (c.get("target"), c.get("hits"), c.get("applied_hits"), c.get("total"))
                      for c in (chain or []))


def _pos_of(dec, uid):
    for u in (dec.get("units") or []):
        if int(u.get("id")) == int(uid):
            p = u.get("pos") or {}
            return (p.get("col"), p.get("row"))
    return None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--rank", default="17")
    # PV bas -> la cible principale tombe TOT (petit `k`), donc `max(0, H - k - 1) > 0` et le REPORT
    # existe des DEUX cotes : c'est la seule facon d'exercer le selecteur de chaine.
    ap.add_argument("--hp-target", type=int, default=900)
    ap.add_argument("--foes", default=FOES_DEFAULT,
                    help="visualId des 4 ennemis, dans l'ordre T,B,D,E")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)

    foes = [(v.strip(), p) for v, p in zip(args.foes.split(","), POS_FOES)]
    if len(foes) != 4:
        print("[523] --foes attend 4 visualId separes par des virgules")
        return 2

    tag = uuid.uuid4().hex[:8]
    tmp = ROOT / "logs" / "probe523"
    tmp.mkdir(parents=True, exist_ok=True)
    bc = tmp / ("seedbc-%s.json" % tag)
    st_file = Path(args.state_file or (tmp / ("state-%s.json" % tag)))
    st_file.parent.mkdir(parents=True, exist_ok=True)

    sid = _resolve_session()
    catalog_inject.write_augmented_seed_bc(str(bc), [CARRIER])
    print("[523] seed BC augmente : %s (%s)" % (bc.name, CARRIER))

    extra = ["--seed", str(args.seed), "--board", args.board, "--rank", str(args.rank),
             "--seed-bc", str(bc), "--p-units", CARRIER,
             "--a-units", ",".join(v for v, _ in foes),
             "--place", "%s:%d,%d" % (CARRIER, POS_CASTER[0], POS_CASTER[1]),
             "--no-ai", "--hp-player", "90000", "--hp-target", str(args.hp_target)]
    for vid, (c, r) in foes:
        extra += ["--a-place", "%s:%d,%d" % (vid, c, r)]
    rid = _build(st_file, extra)
    print("[523] runner=%s session=%s board=%s seed=%s hp-target=%s"
          % (rid, sid, args.board, args.seed, args.hp_target))

    rc = 0
    try:
        mkstate, dec, board = _capture(sid, rid)
        me = _unit_of(dec, CARRIER)
        if me is None:
            print("[523] %s ABSENT du decisionView -- montage a revoir" % CARRIER)
            return 2
        cid = int(me["id"])
        by_vis = {u.get("visualId"): int(u["id"]) for u in _alive_units(dec) if not u.get("ctrl")}
        ids = {vid: by_vis.get(vid) for vid, _ in foes}
        print("[523] caster=u%s @%s ; ennemis %s"
              % (cid, _pos_of(dec, cid),
                 {v: "u%s@%s" % (i, _pos_of(dec, i)) for v, i in ids.items() if i}))

        # Les positions REELLES, pas celles demandees : `--a-place` refuse en silence hors board.
        cpos = _pos_of(dec, cid)
        geo = {}
        for vid, _ in foes:
            uid = ids.get(vid)
            geo[vid] = None if uid is None else hexgeo.distance(cpos, _pos_of(dec, uid))
        print("[523] distances au caster : %s" % geo)

        tid = ids.get(foes[0][0])
        eligible = ids.get(foes[1][0])
        if tid is None or eligible is None:
            print("[523] cible ou relais absent -- montage a revoir")
            return 2
        tpos = _pos_of(dec, tid)
        attendu = [tid]
        for vid, _ in foes[1:]:
            uid = ids.get(vid)
            if uid is None:
                continue
            adj_t = hexgeo.distance(tpos, _pos_of(dec, uid)) == 1
            in_rng = (geo.get(vid) or 99) <= 2
            if adj_t and in_rng:
                attendu.append(uid)
        print("[523] ensemble de report ATTENDU (adjacent a la cible ET <= range 2 du caster) : %s"
              % attendu[1:])

        fh, _tg = _from_here(sid, rid, cid, HEAVY_WARP_FLAMER)
        legal = [t for t in (_tid(x) for x in fh) if t is not None]
        print("[523] cibles LEGALES fromHere : %s" % legal)
        if tid not in legal:
            print("[523] la cible du montage n'est pas LEGALE (portee/melee) -- montage a revoir")
            return 2

        # --- FACE DECISION : le masque `TARGETING_OPTIONS` (DECIDER != EXECUTER) -------------------
        # `abilityTargets(...).fromHere` = ce que le natif accepte SANS bouger ; le port doit rendre
        # 0 exactement sur ces entites-la et un `TargetingRule` non nul sur les autres. Le caster est
        # inclus dans le balayage (masque sans `CasterIsPossibleTarget`).
        from engine.runner.abilities.targeting import get_invalid_target_reason
        from engine.runner.abilities.handler import ABILITY_CLASSES
        st_gate = mkstate()
        ab = ABILITY_CLASSES[HEAVY_WARP_FLAMER]()
        gate_rows, gate_ko = [], []
        for u in _alive_units(dec):
            uid = int(u["id"])
            r = int(get_invalid_target_reason(st_gate, cid, uid, ab))
            attendu_ok = uid in legal
            gate_rows.append((uid, u.get("visualId"), bool(u.get("ctrl")), r, attendu_ok))
            if (r == 0) != attendu_ok:
                gate_ko.append(uid)
        for uid, vis, ctrl, r, ok in gate_rows:
            print("[523]   gate u%-3s %-16s %s reason=%#x  natif_legal=%s"
                  % (uid, vis, "MOI " if ctrl else "ENN ", r, ok))
        print("[523] VERDICT-0 masque de ciblage vs `fromHere` natif : %s -> %s"
              % (gate_ko or "aucun ecart", "OK" if not gate_ko else "MISMATCH"))
        rc |= 0 if not gate_ko else 1

        # --- OFFLINE (chemin reel : le handler) -----------------------------------------------
        st = mkstate()
        diag = _offline_cast(st, cid, tid, HEAVY_WARP_FLAMER)
        off_chain = diag.get("chain") or []
        print("[523] OFFLINE ported=%s dsl=%s hits=%s range=%s"
              % (diag.get("ported"), diag.get("dsl"), diag.get("hits"), diag.get("range")))
        print("[523] OFFLINE chaine : %s" % _fmt_chain(off_chain))
        off_per_hit = {int(c["target"]): [int(x) for x in (c.get("per_hit_health") or [])]
                       for c in off_chain}

        # --- LIVE ------------------------------------------------------------------------------
        res = _cast_live(sid, rid, cid, tid, HEAVY_WARP_FLAMER, capture_events=True)
        live_per_hit = _live_per_hit(res, HEAVY_WARP_FLAMER)
        print("[523] LIVE ok=%s mutated=%s errors=%s"
              % (res.get("ok"), res.get("mutated"), res.get("errors")))
        print("[523] LIVE per-coup par cible : %s"
              % json.dumps({str(k): v for k, v in sorted(live_per_hit.items())}))

        # --- VERDICTS ---------------------------------------------------------------------------
        if diag.get("ported") is not True:
            print("[523] VERDICT-1 ECHEC : `ported` != True -- l'ability est ENCORE un no-op")
            rc = 1
        else:
            print("[523] VERDICT-1 OK : ported=True")

        off_order = [int(c["target"]) for c in off_chain]
        live_order = list(live_per_hit.keys())
        ok2 = off_order == live_order
        print("[523] VERDICT-2a chaine ORDONNEE : offline=%s live=%s -> %s"
              % (off_order, live_order, "OK" if ok2 else "MISMATCH"))
        rc |= 0 if ok2 else 1
        # 2b -- AUCUNE cible HORS de l'ensemble geometrique attendu ne doit etre frappee, ni offline
        # ni live. C'est le verdict qui mord sur les deux CONTRE-EXEMPLES du montage (`D` exclu par
        # la portee depuis le caster, `E` exclu par l'adjacence a la cible) : chacun entrerait dans
        # la chaine si l'un des deux volets de `GetOtherTargets` manquait au port.
        interdits = sorted((set(live_order) | set(off_order)) - set(attendu))
        print("[523] VERDICT-2b cibles HORS de l'ensemble attendu %s : %s -> %s"
              % (attendu, interdits or "aucune", "OK" if not interdits else "MISMATCH"))
        rc |= 0 if not interdits else 1
        # 2c -- quand le report EXISTE, le 2e maillon doit etre EXACTEMENT le relais eligible.
        if len(live_order) > 1:
            ok2c = live_order[1] == eligible
            print("[523] VERDICT-2c 2e maillon LIVE = u%s (relais eligible u%s) -> %s"
                  % (live_order[1], eligible, "OK" if ok2c else "MISMATCH"))
            rc |= 0 if ok2c else 1
        else:
            print("[523] VERDICT-2c NON EXERCE : la chaine LIVE n'a qu'un maillon (aucun report)")

        # Le port APPLIQUE en un bloc la ou le natif cesse d'appliquer sur un cadavre : on compare
        # donc la sequence offline CLAMPEE par les PV (comportement documente de
        # `ChainLeftOverHitsAttackDamage.execute`).
        off_hp0 = {int(c["target"]): int(c.get("hp_before") or 0) for c in off_chain}

        def _clamped(seq, hp):
            out = []
            for h in seq:
                d = max(0, min(int(h), hp))
                out.append(d)
                hp -= d
            return out

        for t in sorted(set(off_per_hit) | set(live_per_hit)):
            o, l = off_per_hit.get(t), live_per_hit.get(t)
            oc = _clamped(o, off_hp0.get(t, 0)) if o is not None else None
            # Le natif CESSE d'emettre des que `UnitExtensions.HasFlag(target, UnitFlag.Overkilled)`
            # est vrai a l'entree d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` : la
            # sequence LIVE est donc un PREFIXE de la sequence offline clampee, dont la queue est
            # NULLE. Le critere confronte le prefixe COMMUN valeur par valeur ET exige que tout ce
            # que le port a applique au-dela vaille 0 -- ni plus laxiste ni plus strict que le natif.
            same = (oc is not None and l is not None and len(oc) >= len(l)
                    and all(int(a) == int(b) for a, b in zip(oc, l))
                    and all(int(x) == 0 for x in oc[len(l):]))
            print("[523] VERDICT-3 u%s per-coup offline(brut)=%s offline(clampe)=%s live=%s -> %s"
                  % (t, o, oc, l, "OK" if same else "ECART"))
            rc |= 0 if same else 1

        # `GetNumTotalHits` : le compteur persistant vaut 0 (la triggered 1546 n'est pas portee et
        # aucune attaque alliee Psychic n'a eu lieu) -> total = nrOfHits.
        from engine.entities.effects.magnitude import ability_var
        nr = int(ability_var("HeavyWarpFlamer", "nrOfHits", is_constant=True) or 0)
        mx = int(ability_var("HeavyWarpFlamer", "maxNrOfHits", is_constant=True) or 0)
        demandes = int(off_chain[0]["hits"]) if off_chain else 0
        applique = int((off_chain[0].get("applied_hits") or 0)) if off_chain else 0
        live_main = len(live_per_hit.get(tid) or [])
        # Le noeud `GetNumTotalHits` doit rendre EXACTEMENT `nrOfHits` : le compteur persistant
        # `(1227, "PSYCHIC_ATTACKS_KEY")` n'est ecrit que par la triggered 1546 (non portee) et
        # aucune attaque alliee Psychic n'a eu lieu -> `Min(0, maxNrOfHits - nrOfHits)` = 0.
        # ⚠ `demandes` (la BASE passee a l'Operation) n'est PAS le nombre de coups APPLIQUES :
        # `AttackHitsWithModifiersFormula` s'interpose (foyer PARTAGE, hors #523). C'est
        # `applied_hits` qu'on confronte au compte d'events LIVE -- et seulement dans le regime NON
        # CLAMPE (cible survivante), ou chaque coup applique emet son event.
        ok4 = (demandes == nr) and (nr <= mx)
        print("[523] VERDICT-4a GetNumTotalHits : nrOfHits=%s maxNrOfHits=%s ; noeud offline=%s -> %s"
              % (nr, mx, demandes, "OK" if ok4 else "MISMATCH"))
        rc |= 0 if ok4 else 1
        survivante = bool(off_chain) and int(off_chain[0].get("hp_before") or 0) > sum(
            int(x) for x in (off_chain[0].get("per_hit_health") or []))
        if survivante:
            ok4b = applique == live_main
            print("[523] VERDICT-4b coups APPLIQUES (regime non clampe) : offline=%s live=%s -> %s"
                  % (applique, live_main, "OK" if ok4b else "MISMATCH"))
            rc |= 0 if ok4b else 1
        else:
            print("[523] VERDICT-4b NON EXERCE : cible TUEE -- le natif cesse d'emettre sur le "
                  "cadavre (offline applique=%s, events live=%s)" % (applique, live_main))

        # `GetLeftOverHits` sans `extraHits` : report = max(0, H - k - 1), 0 si la cible survit.
        if off_chain:
            first = off_chain[0]
            ph = [int(x) for x in (first.get("per_hit_health") or [])]
            hp0 = int(first.get("hp_before") or 0)
            k, acc = None, 0
            for i, h in enumerate(ph):
                acc += h
                if hp0 - acc <= 0:
                    k = i + 1
                    break
            attendu_report = max(0, len(ph) - k - 1) if k else 0
            porte = int(off_chain[1]["hits"]) if len(off_chain) > 1 else 0
            ok5 = attendu_report == porte
            print("[523] VERDICT-5 report : H=%s k=%s -> max(0,H-k-1)=%s ; 2e maillon hits=%s -> %s"
                  % (len(ph), k, attendu_report, porte, "OK" if ok5 else "MISMATCH"))
            rc |= 0 if ok5 else 1
            if attendu_report == 0:
                print("[523] AVERTISSEMENT : report NUL -- baisser --hp-target pour exercer la "
                      "chaine (la cible doit tomber AVANT l'avant-dernier coup)")
    finally:
        if not args.keep:
            _dispose(st_file)
            bc.unlink(missing_ok=True)
    print("[523] rc=%s" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
