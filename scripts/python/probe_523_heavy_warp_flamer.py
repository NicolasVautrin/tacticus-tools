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
from engine.entities.effects.magnitude import ability_var                        # noqa: E402
from engine.runner.abilities.thousandsons import HEAVY_WARP_FLAMER_ID            # noqa: E402

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


def clamped(seq, hp):
    """La sequence offline CLAMPEE par les PV : le port applique en UN bloc la ou le natif cesse
    d'appliquer sur un cadavre (comportement documente de `ChainLeftOverHitsAttackDamage.execute`)."""
    out = []
    for h in seq:
        d = max(0, min(int(h), hp))
        out.append(d)
        hp -= d
    return out


def left_over_attendu(maillon):
    """`(H, k, GetLeftOverHits(maillon))` du 1er maillon -- `extraHits` NULL pour 1194.

    ⚠ Cette fonction NE RE-IMPLEMENTE PLUS la loi, elle DELEGUE au foyer (#489-r1, 2026-08-15).
    La raison est une mesure : la loi du foyer est INCOMPLETE (residu `#489-r2`) et les deux
    correctifs << evidents >> sont refutes LIVE -- un jumeau qui recopierait une formule
    comparerait donc le port a une formule perimee au lieu de le comparer au LIVE, ce qui est
    exactement la tautologie que #489-r1 reprochait au VERDICT-4 de `probe_489`. Le maillon
    porte desormais `overkilled` / `overkill_at_hit`, l'entree qui manque a la loi."""
    from engine.runner.abilities.behaviours.combat import ChainLeftOverHitsAttackDamage
    ph = [int(x) for x in (maillon.get("per_hit_health") or [])]
    hp0 = int(maillon.get("hp_before") or 0)
    k, acc = None, 0
    for i, h in enumerate(ph):
        acc += h
        if hp0 - acc <= 0:
            k = i + 1
            break
    return len(ph), k, ChainLeftOverHitsAttackDamage._left_over_hits(maillon, 0)


def mesure(sid, st_file, *, seed=4242, board="MC1_67", rank="17", hp_target=3300, relay_hp=None,
           foes_ids=FOES_DEFAULT, caster_pos=POS_CASTER, foes_pos=None, keep=False):
    """MONTE le montage, CAPTURE l'etat, rejoue le cast OFFLINE puis LIVE, et rend les MESURES --
    sans aucun verdict (les verdicts vivent dans `verdicts()` et dans le test de garde).

    Rend `None` si le build echoue (host/session indisponible), jamais un dict partiel."""
    pos = list(foes_pos or POS_FOES)
    foes = [(v.strip(), p) for v, p in zip(foes_ids.split(","), pos)]
    if len(foes) != 4:
        raise ValueError("le montage attend 4 ennemis (T, B, D, E)")

    st_file = Path(st_file)
    st_file.parent.mkdir(parents=True, exist_ok=True)
    bc = st_file.with_name(st_file.stem + "-seedbc.json")
    catalog_inject.write_augmented_seed_bc(str(bc), [CARRIER])

    extra = ["--seed", str(seed), "--board", board, "--rank", str(rank),
             "--seed-bc", str(bc), "--p-units", CARRIER,
             "--a-units", ",".join(v for v, _ in foes),
             "--place", "%s:%d,%d" % (CARRIER, caster_pos[0], caster_pos[1]),
             "--no-ai", "--hp-player", "90000", "--hp-target", str(hp_target)]
    for vid, (c, r) in foes:
        extra += ["--a-place", "%s:%d,%d" % (vid, c, r)]
    if relay_hp is not None:
        extra += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (foes[1][0], relay_hp, relay_hp)]
    rid = _build(st_file, extra)

    try:
        mkstate, dec, _board = _capture(sid, rid)
        me = _unit_of(dec, CARRIER)
        if me is None:
            raise RuntimeError("%s ABSENT du decisionView -- montage a revoir" % CARRIER)
        cid = int(me["id"])
        by_vis = {u.get("visualId"): int(u["id"]) for u in _alive_units(dec) if not u.get("ctrl")}
        ids = {vid: by_vis.get(vid) for vid, _ in foes}
        cpos = _pos_of(dec, cid)
        # Les positions REELLES, pas celles demandees : `--a-place` verifie, mais la mesure doit
        # porter sur ce qui EST, jamais sur ce qui a ete demande.
        geo = {vid: (None if ids.get(vid) is None
                     else hexgeo.distance(cpos, _pos_of(dec, ids[vid]))) for vid, _ in foes}
        tid, eligible = ids.get(foes[0][0]), ids.get(foes[1][0])
        if tid is None or eligible is None:
            raise RuntimeError("cible ou relais absent -- montage a revoir")
        tpos = _pos_of(dec, tid)
        attendu = [tid]
        for vid, _ in foes[1:]:
            uid = ids.get(vid)
            if uid is None:
                continue
            if hexgeo.distance(tpos, _pos_of(dec, uid)) == 1 and (geo.get(vid) or 99) <= 2:
                attendu.append(uid)

        fh, _tg = _from_here(sid, rid, cid, HEAVY_WARP_FLAMER)
        legal = [t for t in (_tid(x) for x in fh) if t is not None]

        # FACE DECISION -- `abilityTargets(...).fromHere` = ce que le natif accepte SANS bouger ;
        # le port doit rendre 0 exactement sur ces entites-la. Le caster est dans le balayage
        # (le masque ne porte pas `CasterIsPossibleTarget`).
        from engine.runner.abilities.handler import ABILITY_CLASSES
        from engine.runner.abilities.targeting import get_invalid_target_reason
        st_gate = mkstate()
        ab = ABILITY_CLASSES[HEAVY_WARP_FLAMER]()
        gate = [{"id": int(u["id"]), "visualId": u.get("visualId"), "mine": bool(u.get("ctrl")),
                 "reason": int(get_invalid_target_reason(st_gate, cid, int(u["id"]), ab)),
                 "natif_legal": int(u["id"]) in legal} for u in _alive_units(dec)]

        # OFFLINE -- le CHEMIN REEL (le handler), depuis la capture prise AVANT le cast natif.
        diag = _offline_cast(mkstate(), cid, tid, HEAVY_WARP_FLAMER)
        off_chain = diag.get("chain") or []
        # LIVE -- le MEME cast.
        res = _cast_live(sid, rid, cid, tid, HEAVY_WARP_FLAMER, capture_events=True)
        live_per_hit = _live_per_hit(res, HEAVY_WARP_FLAMER)

        return {
            "runner": rid, "board": board, "seed": seed, "hp_target": hp_target,
            "caster": cid, "caster_pos": cpos, "target": tid, "eligible": eligible,
            "ids": ids, "geo": geo, "attendu": attendu, "legal": legal, "gate": gate,
            "hp_of": {int(u["id"]): int(u.get("hp") or 0) for u in _alive_units(dec)},
            "port": diag, "off_chain": off_chain,
            "off_per_hit": {int(c["target"]): [int(x) for x in (c.get("per_hit_health") or [])]
                            for c in off_chain},
            "off_hp0": {int(c["target"]): int(c.get("hp_before") or 0) for c in off_chain},
            "live": {"ok": res.get("ok"), "errors": res.get("errors")},
            "live_per_hit": live_per_hit,
            "nr_of_hits": int(ability_var(HEAVY_WARP_FLAMER_ID, "nrOfHits", is_constant=True) or 0),
            "max_nr_of_hits": int(ability_var(HEAVY_WARP_FLAMER_ID, "maxNrOfHits",
                                              is_constant=True) or 0),
        }
    finally:
        if not keep:
            _dispose(st_file)
            bc.unlink(missing_ok=True)


def verdicts(m):
    """Les verdicts, DERIVES des mesures -- rend `(rc, lignes)`. Le test de garde assertionne les
    MEMES criteres sur le MEME dict : un seul foyer, jamais deux jeux de seuils."""
    out, rc = [], 0
    add = out.append
    add("[523] runner=%s board=%s seed=%s hp-target=%s"
        % (m["runner"], m["board"], m["seed"], m["hp_target"]))
    add("[523] caster=u%s @%s ; distances au caster : %s" % (m["caster"], m["caster_pos"], m["geo"]))
    add("[523] ensemble de report ATTENDU (adjacent a la cible ET <= range du caster) : %s"
        % m["attendu"][1:])
    add("[523] cibles LEGALES fromHere : %s" % m["legal"])
    for g in m["gate"]:
        add("[523]   gate u%-3s %-16s %s reason=%#x  natif_legal=%s"
            % (g["id"], g["visualId"], "MOI " if g["mine"] else "ENN ", g["reason"],
               g["natif_legal"]))
    gate_ko = [g["id"] for g in m["gate"] if (g["reason"] == 0) != g["natif_legal"]]
    add("[523] VERDICT-0 masque de ciblage vs `fromHere` natif : %s -> %s"
        % (gate_ko or "aucun ecart", "OK" if not gate_ko else "MISMATCH"))
    rc |= 0 if not gate_ko else 1

    add("[523] OFFLINE ported=%s dsl=%s hits=%s range=%s"
        % (m["port"].get("ported"), m["port"].get("dsl"), m["port"].get("hits"),
           m["port"].get("range")))
    add("[523] OFFLINE chaine : %s" % _fmt_chain(m["off_chain"]))
    add("[523] LIVE ok=%s errors=%s ; per-coup par cible : %s"
        % (m["live"]["ok"], m["live"]["errors"],
           json.dumps({str(k): v for k, v in sorted(m["live_per_hit"].items())})))

    ok1 = m["port"].get("ported") is True
    add("[523] VERDICT-1 ported=%s -> %s" % (m["port"].get("ported"), "OK" if ok1 else "ECHEC"))
    rc |= 0 if ok1 else 1

    off_order = [int(c["target"]) for c in m["off_chain"]]
    live_order = list(m["live_per_hit"].keys())
    ok2a = off_order == live_order
    add("[523] VERDICT-2a chaine ORDONNEE : offline=%s live=%s -> %s"
        % (off_order, live_order, "OK" if ok2a else "MISMATCH"))
    rc |= 0 if ok2a else 1
    # 2b -- AUCUNE cible HORS de l'ensemble geometrique attendu, ni offline ni live. C'est le verdict
    # qui mord sur les deux CONTRE-EXEMPLES du montage (`D` exclu par la portee depuis le caster,
    # `E` exclu par l'adjacence a la cible) : chacun entrerait si un volet manquait au port.
    interdits = sorted((set(live_order) | set(off_order)) - set(m["attendu"]))
    add("[523] VERDICT-2b cibles HORS de l'ensemble attendu %s : %s -> %s"
        % (m["attendu"], interdits or "aucune", "OK" if not interdits else "MISMATCH"))
    rc |= 0 if not interdits else 1
    # 2c -- quand le report EXISTE, le 2e maillon appartient a l'ensemble ELIGIBLE. Quand cet
    # ensemble a PLUSIEURS membres, c'est `SortTargetsByDamagePredictionSelector` qui tranche LEQUEL,
    # et le verdict qui mord est alors 2a : on imprime ici de quoi le lire (PV des candidats).
    if len(live_order) > 1:
        ok2c = live_order[1] in m["attendu"][1:]
        add("[523] VERDICT-2c 2e maillon LIVE = u%s ; eligibles %s -> %s"
            % (live_order[1], {u: m["hp_of"].get(u) for u in m["attendu"][1:]},
               "OK" if ok2c else "MISMATCH"))
        rc |= 0 if ok2c else 1
    else:
        add("[523] VERDICT-2c NON EXERCE : la chaine LIVE n'a qu'un maillon (aucun report)")

    for t in sorted(set(m["off_per_hit"]) | set(m["live_per_hit"])):
        o, l = m["off_per_hit"].get(t), m["live_per_hit"].get(t)
        oc = clamped(o, m["off_hp0"].get(t, 0)) if o is not None else None
        # Le natif CESSE d'emettre des que `UnitExtensions.HasFlag(target, UnitFlag.Overkilled)` est
        # vrai a l'entree d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` : la sequence LIVE
        # est un PREFIXE de la sequence offline clampee, dont la queue est NULLE. Le critere
        # confronte le prefixe COMMUN valeur par valeur ET exige que la queue vaille 0.
        same = (oc is not None and l is not None and len(oc) >= len(l)
                and all(int(a) == int(b) for a, b in zip(oc, l))
                and all(int(x) == 0 for x in oc[len(l):]))
        add("[523] VERDICT-3 u%s per-coup offline(brut)=%s offline(clampe)=%s live=%s -> %s"
            % (t, o, oc, l, "OK" if same else "ECART"))
        rc |= 0 if same else 1

    nr, mx = m["nr_of_hits"], m["max_nr_of_hits"]
    demandes = int(m["off_chain"][0]["hits"]) if m["off_chain"] else 0
    applique = int(m["off_chain"][0].get("applied_hits") or 0) if m["off_chain"] else 0
    live_main = len(m["live_per_hit"].get(m["target"]) or [])
    ok4a = (demandes == nr) and (nr <= mx)
    add("[523] VERDICT-4a GetNumTotalHits : nrOfHits=%s maxNrOfHits=%s ; noeud offline=%s -> %s"
        % (nr, mx, demandes, "OK" if ok4a else "MISMATCH"))
    rc |= 0 if ok4a else 1
    # `demandes` (la BASE passee a l'Operation) n'est PAS le nombre de coups APPLIQUES :
    # `AttackHitsWithModifiersFormula` s'interpose (foyer PARTAGE, hors #523). C'est `applied_hits`
    # qu'on confronte au compte d'events LIVE -- et SEULEMENT dans le regime non clampe.
    if m["off_chain"] and m["off_hp0"].get(m["target"], 0) > sum(
            m["off_per_hit"].get(m["target"], [])):
        ok4b = applique == live_main
        add("[523] VERDICT-4b coups APPLIQUES (regime non clampe) : offline=%s live=%s -> %s"
            % (applique, live_main, "OK" if ok4b else "MISMATCH"))
        rc |= 0 if ok4b else 1
    else:
        add("[523] VERDICT-4b NON EXERCE : cible TUEE -- le natif cesse d'emettre sur le cadavre "
            "(offline applique=%s, events live=%s)" % (applique, live_main))

    if m["off_chain"]:
        H, k, att = left_over_attendu(m["off_chain"][0])
        porte = int(m["off_chain"][1]["hits"]) if len(m["off_chain"]) > 1 else 0
        ok5 = att == porte
        add("[523] VERDICT-5 report : H=%s k=%s -> max(0,H-k-1)=%s ; 2e maillon hits=%s -> %s"
            % (H, k, att, porte, "OK" if ok5 else "MISMATCH"))
        rc |= 0 if ok5 else 1
        if att == 0:
            add("[523] AVERTISSEMENT : report NUL -- baisser --hp-target pour exercer la chaine")
    return rc, out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--rank", default="17")
    # PV bas -> la cible principale tombe TOT (petit `k`), donc `max(0, H - k - 1) > 0` et le REPORT
    # existe des DEUX cotes : c'est la seule facon d'exercer le selecteur de chaine.
    ap.add_argument("--hp-target", type=int, default=3300)
    ap.add_argument("--foes", default=FOES_DEFAULT,
                    help="visualId des 4 ennemis, dans l'ordre T,B,D,E")
    # PV du RELAIS, distincts de `--hp-target` : c'est la seule facon de COMPTER les coups reportes
    # dans le live. Un relais qui meurt au 1er coup n'emet plus rien ensuite -- son nombre d'events
    # ne dit alors PAS combien de coups lui ont ete demandes.
    ap.add_argument("--relay-hp", type=int, default=None)
    # GEOMETRIE pilotable : le montage par defaut est UNE configuration ; toute autre qui respecte
    # les cinq contraintes de l'en-tete est aussi valable, et en jouer plusieurs est ce qui separe
    # « le port marche ici » de « le port marche ».
    ap.add_argument("--caster-pos", default="%d,%d" % POS_CASTER)
    ap.add_argument("--foes-pos", default=";".join("%d,%d" % p for p in POS_FOES),
                    help="tuiles des 4 ennemis 'c,r;c,r;c,r;c,r' dans l'ordre T,B,D,E")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)

    tmp = ROOT / "logs" / "probe523"
    tmp.mkdir(parents=True, exist_ok=True)
    st_file = Path(args.state_file or (tmp / ("state-%s.json" % uuid.uuid4().hex[:8])))
    sid = _resolve_session()
    m = mesure(sid, st_file, seed=args.seed, board=args.board, rank=args.rank,
               hp_target=args.hp_target, relay_hp=args.relay_hp, foes_ids=args.foes,
               caster_pos=tuple(int(x) for x in args.caster_pos.split(",")),
               foes_pos=[tuple(int(x) for x in seg.split(",")) for seg in args.foes_pos.split(";")],
               keep=args.keep)
    rc, lignes = verdicts(m)
    print("\n".join(lignes))
    print("[523] rc=%s" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


