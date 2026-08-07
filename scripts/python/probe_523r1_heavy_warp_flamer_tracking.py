#!/usr/bin/env python
"""Probe #523-r1 -- confront LIVE de la triggered `1546 HeavyWarpFlamer_AttackTracking`, le COMPTEUR
de coups psychiques ALLIES que lit `HeavyWarpFlamerAbility$$GetNumExtraHits`.

LE CRITERE, avant toute methode : **le compteur avance-t-il aux memes moments et de la meme quantite
que chez le natif ?** L'observable est le NOMBRE DE COUPS du `1227 HeavyWarpFlamer` -- le compteur
lui-meme n'a AUCUN canal de lecture live (`dumpEntityComponents` rend la MISE EN PAGE des composants,
pas leurs VALEURS). Le regime est donc DISCRIMINANT par construction : deux casts successifs du MEME
porteur, sur le MEME montage, dont le nombre de coups DOIT changer.

    tour 1 : deux allies PSYCHIQUES attaquent (+1 chacun) + un allie PHYSIQUE attaque (+0)
             -> le cast rend `nrOfHits + 2` coups
    tour 2 : personne n'attaque avant le cast (et `On(TurnEnd)` a vide la cle entre-temps)
             -> le cast rend `nrOfHits` coups

Un port qui ne compterait RIEN rendrait `nrOfHits` aux DEUX tours ; un port qui compterait aussi
l'allie PHYSIQUE rendrait `nrOfHits + 3` au tour 1 ; un port qui ne VIDERAIT pas rendrait
`nrOfHits + 2` au tour 2. Les trois modes de panne sont donc separes par le MEME montage.

MONTAGE -- LA GEOMETRIE EST FABRIQUEE (`--place` / `--a-place`), PAS SUBIE. Sur `MC1_67` (7x9) :

    C  = `thousSekhetar` (0,0)   -- ADJACENT A AUCUN ennemi, sinon `ForceMeleeTarget` rabat la portee
    T  = cible du flamer (0,2)   -- d(C,T) = 2 = `range` ; AUCUN autre ennemi a <= 2 de C ET adjacent
                                    a T -> l'ensemble de report est VIDE, la chaine a UN maillon
    A1 = `thousSorcerer` (4,0)   -- arme RANGED `Psychic` (portee 2) ; sac de frappe P1 (4,2), d = 2
    A2 = `thousAhriman`  (6,0)   -- arme RANGED `Psychic` (portee 2) ; sac de frappe P2 (6,2), d = 2
    A3 = `astraBullgryn` (4,3)   -- arme MELEE `Physical` SEULE ; frappe P1 (4,2), d = 1  [TEMOIN]

A1/A2 sont a distance 2 de leur sac : c'est ce qui fait choisir leur arme RANGED (`Psychic`) et non
leur arme de melee (`Flame` pour les deux Thousand Sons) -- la distance EST le discriminant de profil,
et c'est pourquoi elle est PLACEE, pas subie. A3 n'a QU'UNE arme, `Physical` : son attaque traverse
exactement le meme vecteur `On(9)` que les deux autres et doit ne RIEN ajouter.

GATE DE CONFRONTABILITE : le porteur est un HERO `lineup` ABSENT du seed BC partage -> il entre par
`catalog_inject.write_augmented_seed_bc` + `rl_duel build --seed-bc` (`case-92` SS6), la MEME voie
que #523 et #27. Les cinq autres unites sont AU POOL.

CE QUI EST CONFRONTE, etage par etage (jamais un scalaire agrege) :
  0. le montage    -- profils REELLEMENT emis par chaque attaque d'allie (offline), et distances
                      REELLES (pas celles demandees) ;
  1. le COMPTEUR   -- valeur de `(1227, "PSYCHIC_ATTACKS_KEY")` sur le porteur APRES CHAQUE attaque
                      d'allie, cote OFFLINE (le seul cote ou il est lisible) ;
  2. `GetNumTotalHits` -- le noeud `hits` de la feuille, offline, tour 1 et tour 2 ;
  3. les COUPS APPLIQUES -- offline vs LIVE, par cible, coup par coup, aux DEUX tours ;
  4. le DELTA      -- `coups(tour 1) - coups(tour 2)`, des DEUX cotes : c'est lui qui rend le regime
                      non degenere (un accord a valeur constante ne prouverait rien) ;
  5. la BRANCHE `On(TurnEnd)` -- OFFLINE : le compteur est NON NUL, le vecteur fin-de-tour est joue,
                      la cle DOIT disparaitre. (Cote LIVE elle est attestee par le tour 2, dont le
                      nombre de coups retombe a la base.)

ASCII only (cp1252). Usage :
    python probe_523r1_heavy_warp_flamer_tracking.py [--seed 4242] [--board MC1_67] [--state-file P]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import catalog_inject                                                            # noqa: E402
import hexgeo                                                                    # noqa: E402
from probe_116_necrons import (_alive_units, _build, _capture, _cast_live,       # noqa: E402
                               _dispose, _from_here, _live_per_hit, _r, _tid, _unit_of)
from rl_collect_batch import _resolve_session                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                # noqa: E402
from engine.entities.effects.magnitude import ability_var                        # noqa: E402
from engine.runner.abilities.thousandsons import HEAVY_WARP_FLAMER_ID            # noqa: E402
from engine.runner.operations.triggers.loki.heavy_warp_flamer import STACK_KEY   # noqa: E402

ROOT = PYDIR.parents[1]
HEAVY_WARP_FLAMER = int(ActiveAbilityType.HeavyWarpFlamer)                       # 1227
CARRIER = "thousSekhetar"
#: (visualId, tuile) des allies, dans l'ordre d'attaque. Les DEUX premiers portent une arme RANGED
#: `Psychic` (portee 2) ; le TROISIEME n'a qu'une arme MELEE `Physical` -- c'est le TEMOIN du conjoint
#: `CurrentAttackDamageProfilesContain(Psychic)`.
ALLIES = [("thousSorcerer", (4, 0)), ("thousAhriman", (6, 0)), ("astraBullgryn", (4, 3))]
#: le sac de frappe de chaque allie, MEME ordre. A1 -> P1 (d=2), A2 -> P2 (d=2), A3 -> P1 (d=1).
ALLY_TARGET_IDX = [1, 2, 1]
POS_CASTER = (0, 0)
#: (visualId, tuile) des ennemis : T (cible du flamer), P1, P2 (sacs de frappe, hors de portee de C).
FOES = [("necroWarden", (0, 2)), ("orksNob", (4, 2)), ("tauCrisis", (6, 2))]


def _pos_of(dec, uid):
    for u in (dec.get("units") or []):
        if int(u.get("id")) == int(uid):
            p = u.get("pos") or {}
            return (p.get("col"), p.get("row"))
    return None


def _normal_ability(dec, uid):
    """`ActiveAbilityComponent.NormalAttackType@0x28` -- l'id CONCRET de l'attaque normale de
    l'unite, LU dans `decisionView` (`kind == "normal"`), jamais devine
    (`project_ability_normal_attack_concrete`)."""
    for u in (dec.get("units") or []):
        if int(u.get("id")) == int(uid):
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    return int(ab["id"])
    return None


def _counter(state, owner_id):
    """La valeur de la cle `(1227, "PSYCHIC_ATTACKS_KEY")` sur le porteur, cote OFFLINE.
    `None` = cle absente (ce que `GetPersistentDataFormula$$Calculate` rend comme 0)."""
    from engine.runner.components import persistent_data
    return persistent_data(state.get_entity(int(owner_id)), (HEAVY_WARP_FLAMER, STACK_KEY))


def _offline_sequence(mkstate, cid, tid, allies, ally_targets, *, with_attacks: bool):
    """Rejoue la sequence OFFLINE par le CHEMIN REEL (`Runner` + ses handlers par defaut) et rend
    la trace ETAGE PAR ETAGE. `with_attacks=False` = le cast NU (le bras de base)."""
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
    st = mkstate()
    rr = Runner(st).install_default_handlers()
    trace = [{"etape": "depart", "compteur": _counter(st, cid)}]
    profils = []
    if with_attacks:
        for (aid, pid) in zip(allies, ally_targets):
            rr.apply(AttackUnitMessage(int(aid), int(pid)))
            last = rr.damage_handler.last or {}
            profils.append(last.get("profile"))
            trace.append({"etape": "attaque u%s -> u%s" % (aid, pid),
                          "profil": last.get("profile"),
                          "mti": (st.rng.mti if st.rng is not None else None),
                          "compteur": _counter(st, cid)})
    # POSITION DU PRNG juste AVANT le cast : c'est ce qui rend COMPARABLE (ou non) le degat par coup.
    # Un prelude d'attaques qui ne consomme pas le MEME nombre de tirages des deux cotes decale la
    # sequence -- l'ecart qui en resulte est alors de la MAGNITUDE, jamais du NOMBRE DE COUPS.
    rng_avant_cast = ({"mti": st.rng.mti, "mt": list(st.rng.mt)} if st.rng is not None else None)
    rr.apply(ActiveAbilityMessage(caster_id=int(cid), target_id=int(tid),
                                  ability_type=HEAVY_WARP_FLAMER))
    diag = rr.ability_handler.last or {}
    chain = diag.get("chain") or []
    return {"trace": trace, "profils": profils, "diag": diag, "chain": chain,
            "rng_avant_cast": rng_avant_cast,
            "compteur_avant_cast": trace[-1]["compteur"],
            "per_hit": {int(c["target"]): [int(x) for x in (c.get("per_hit_health") or [])]
                        for c in chain},
            "hp0": {int(c["target"]): int(c.get("hp_before") or 0) for c in chain},
            "hits": (int(chain[0]["hits"]) if chain else None),
            "applied": (int(chain[0].get("applied_hits") or 0) if chain else 0)}


def _offline_turn_end(mkstate, cid, tid, allies, ally_targets):
    """BRANCHE `On(TurnEnd)` -- OFFLINE, et c'est le SEUL cote ou elle est falsifiable : on remplit le
    compteur (deux attaques psychiques), on joue le vecteur FIN DE TOUR, et la cle doit DISPARAITRE.
    Rend (compteur_avant, compteur_apres, hits_apres)."""
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
    from engine.runner.operations.triggers.dispatch.turn import end_turn_summon_triggers
    st = mkstate()
    rr = Runner(st).install_default_handlers()
    for (aid, pid) in zip(allies, ally_targets):
        rr.apply(AttackUnitMessage(int(aid), int(pid)))
    avant = _counter(st, cid)
    end_turn_summon_triggers(st, int(st.current_player_id or 0))
    apres = _counter(st, cid)
    rr.apply(ActiveAbilityMessage(caster_id=int(cid), target_id=int(tid),
                                  ability_type=HEAVY_WARP_FLAMER))
    ch = (rr.ability_handler.last or {}).get("chain") or []
    return avant, apres, (int(ch[0]["hits"]) if ch else None)


def clamped(seq, hp):
    """La sequence offline CLAMPEE par les PV -- le MEME critere que `probe_523.clamped` : le port
    applique tous ses coups en un bloc la ou le natif CESSE d'appliquer des que
    `UnitExtensions.HasFlag(target, UnitFlag.Overkilled)` est vrai a l'entree d'
    `IdunBattle.Operations.ApplyDamageOperation$$Execute`. La sequence LIVE est donc un PREFIXE de
    la sequence clampee, dont la queue est NULLE."""
    out = []
    for h in seq:
        d = max(0, min(int(h), hp))
        out.append(d)
        hp -= d
    return out


def _replace_caster(sid, rid, dec, cid, tid, foe_ids):
    """RE-FABRIQUE la geometrie du cast apres le tour adverse : deplace le caster sur une tuile
    LEGALE (`aiMovableTiles`) a distance EXACTEMENT `range`(2) de la cible et a distance >= 2 de
    TOUT ennemi -- `ForceMeleeTarget` du preset `+0x140` rabat la portee a 1 des que le caster est
    au contact (cf. `case-523` SS1), donc une tuile adjacente a un ennemi rendrait le cast illegal
    pour une raison qui n'a rien a voir avec ce qu'on mesure. Rend la tuile choisie, ou None."""
    tp = _pos_of(dec, tid)
    if tp is None or tp[0] is None:
        return None
    autres = [_pos_of(dec, f) for f in foe_ids if int(f) != int(tid)]
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    tiles = []
    for mu in (mov.get("units") or []):
        if int(mu.get("unitId") or -1) == int(cid):
            tiles = [(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                     if t.get("col") is not None]
    cand = [t for t in tiles
            if hexgeo.distance(t, tp) == 2
            and all(p is None or p[0] is None or hexgeo.distance(t, p) >= 2 for p in autres)]
    if not cand:
        return None
    best = cand[0]
    r = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(cid), "to": {"col": best[0], "row": best[1]}}}, 60)
    return best if r.get("ok") else None


def _act(st_file: Path, *args):
    return subprocess.run([sys.executable, "rl_duel.py", *args, "--state-file", str(st_file)],
                          cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def mesure(sid, st_file, *, seed=4242, board="MC1_67", rank="17", hp=60000, keep=False):
    """MONTE le montage, joue les DEUX tours, et rend les MESURES -- sans aucun verdict."""
    st_file = Path(st_file)
    st_file.parent.mkdir(parents=True, exist_ok=True)
    bc = st_file.with_name(st_file.stem + "-seedbc.json")
    catalog_inject.write_augmented_seed_bc(str(bc), [CARRIER])

    extra = ["--seed", str(seed), "--board", board, "--rank", str(rank), "--seed-bc", str(bc),
             "--p-units", ",".join([CARRIER] + [v for v, _ in ALLIES]),
             "--a-units", ",".join(v for v, _ in FOES),
             "--place", "%s:%d,%d" % (CARRIER, POS_CASTER[0], POS_CASTER[1]),
             "--no-ai", "--hp-player", "90000", "--hp-target", str(hp)]
    for vid, (c, r) in ALLIES:
        extra += ["--place", "%s:%d,%d" % (vid, c, r)]
    for vid, (c, r) in FOES:
        extra += ["--a-place", "%s:%d,%d" % (vid, c, r)]
    rid = _build(st_file, extra)

    try:
        mkstate, dec, _board = _capture(sid, rid)
        me = _unit_of(dec, CARRIER)
        if me is None:
            raise RuntimeError("%s ABSENT du decisionView -- montage a revoir" % CARRIER)
        cid = int(me["id"])
        mine = {u.get("visualId"): int(u["id"]) for u in _alive_units(dec) if u.get("ctrl")}
        foes = {u.get("visualId"): int(u["id"]) for u in _alive_units(dec) if not u.get("ctrl")}
        allies = [mine.get(v) for v, _ in ALLIES]
        foe_ids = [foes.get(v) for v, _ in FOES]
        if any(a is None for a in allies) or any(f is None for f in foe_ids):
            raise RuntimeError("allies=%s ennemis=%s -- montage a revoir" % (allies, foe_ids))
        ally_targets = [foe_ids[i] for i in ALLY_TARGET_IDX]
        tid = foe_ids[0]
        cpos = _pos_of(dec, cid)
        # Les distances REELLES, jamais celles demandees : c'est la distance qui choisit l'ARME
        # (donc le PROFIL) de chaque allie, et c'est elle qu'on doit lire.
        geo = {"C->T": hexgeo.distance(cpos, _pos_of(dec, tid)),
               **{"A%d->cible" % (i + 1): hexgeo.distance(_pos_of(dec, allies[i]),
                                                          _pos_of(dec, ally_targets[i]))
                  for i in range(len(allies))},
               **{"C->%s" % FOES[i][0]: hexgeo.distance(cpos, _pos_of(dec, foe_ids[i]))
                  for i in range(len(foe_ids))}}
        pid = mkstate().current_player_id

        fh, _tg = _from_here(sid, rid, cid, HEAVY_WARP_FLAMER)
        legal = [t for t in (_tid(x) for x in fh) if t is not None]

        # ---- OFFLINE (les deux bras, depuis la MEME capture de depart) -------------------------
        off_apres = _offline_sequence(mkstate, cid, tid, allies, ally_targets, with_attacks=True)
        off_base = _offline_sequence(mkstate, cid, tid, allies, ally_targets, with_attacks=False)
        te_avant, te_apres, te_hits = _offline_turn_end(mkstate, cid, tid, allies[:2],
                                                        ally_targets[:2])

        # ---- LIVE tour 1 : les trois attaques d'allie, PUIS le cast ----------------------------
        att_live = []
        for (aid, pid_t) in zip(allies, ally_targets):
            na = _normal_ability(dec, aid)
            res = _cast_live(sid, rid, aid, pid_t, na, capture_events=True)
            att_live.append({"ally": aid, "target": pid_t, "normal": na,
                             "ok": res.get("ok"), "errors": res.get("errors"),
                             # position du PRNG APRES CETTE attaque : c'est ce qui LOCALISE l'etage
                             # ou le port cesse de consommer autant de tirages que le natif.
                             "mti": (_r(sid, "dumpRng", {"runnerId": rid}, 30) or {}).get("mti")})
        rng_live = _r(sid, "dumpRng", {"runnerId": rid}, 30)     # AVANT le cast, cf. `_offline_sequence`
        res1 = _cast_live(sid, rid, cid, tid, HEAVY_WARP_FLAMER, capture_events=True)
        live1 = _live_per_hit(res1, HEAVY_WARP_FLAMER)

        # ---- LIVE tour 2 : fin de mon tour, tour adverse, puis le MEME cast SANS prelude ---------
        # `act endturn` ne clot QUE le tour du camp pilote : un second `endturn` ne rend PAS la main
        # (mesure de la 1re passe -- `legal=[]` au tour 2 avec la cible POURTANT restee a d = 2).
        # Il faut donc `aiturn` pour que le camp adverse joue et rende le tour. Consequence : l'IA
        # DEPLACE ses unites, donc la geometrie du tour 1 n'est plus acquise -- on la RE-FABRIQUE
        # (doctrine : on deplace les unites pour realiser la condition testee, on ne la subit pas).
        _act(st_file, "act", "endturn")
        _act(st_file, "aiturn")
        repositionne = None
        mkstate2, dec2, _b2 = _capture(sid, rid)
        fh2, _tg2 = _from_here(sid, rid, cid, HEAVY_WARP_FLAMER)
        legal2 = [t for t in (_tid(x) for x in fh2) if t is not None]
        if tid not in legal2:
            repositionne = _replace_caster(sid, rid, dec2, cid, tid, foe_ids)
            mkstate2, dec2, _b2 = _capture(sid, rid)
            fh2, _tg2 = _from_here(sid, rid, cid, HEAVY_WARP_FLAMER)
            legal2 = [t for t in (_tid(x) for x in fh2) if t is not None]
        cpos2 = _pos_of(dec2, cid)
        tpos2 = _pos_of(dec2, tid)
        off2 = (_offline_sequence(mkstate2, cid, tid, allies, ally_targets, with_attacks=False)
                if tid in legal2 else None)
        res2 = (_cast_live(sid, rid, cid, tid, HEAVY_WARP_FLAMER, capture_events=True)
                if tid in legal2 else {})
        live2 = _live_per_hit(res2, HEAVY_WARP_FLAMER) if tid in legal2 else {}

        return {
            "runner": rid, "board": board, "seed": seed, "player": pid,
            "caster": cid, "caster_pos": cpos, "target": tid, "allies": allies,
            "ally_targets": ally_targets, "foes": foe_ids, "geo": geo, "legal": legal,
            "off_apres": off_apres, "off_base": off_base,
            "turn_end": {"avant": te_avant, "apres": te_apres, "hits": te_hits},
            "att_live": att_live, "rng_live_avant_cast": rng_live,
            "live1": live1, "live1_ok": res1.get("ok"), "live1_err": res1.get("errors"),
            "tour2": {"legal": legal2, "caster_pos": cpos2, "target_pos": tpos2,
                      "repositionne": repositionne, "off": off2, "live": live2},
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
    add("[523r1] runner=%s board=%s seed=%s player=%s" % (m["runner"], m["board"], m["seed"],
                                                          m["player"]))
    add("[523r1] caster=u%s @%s cible=u%s ; distances REELLES : %s"
        % (m["caster"], m["caster_pos"], m["target"], m["geo"]))
    add("[523r1] cibles LEGALES fromHere (tour 1) : %s" % m["legal"])

    # --- VERDICT-0 : le MONTAGE est-il celui qu'on croit ? (profils REELLEMENT emis) -------------
    profs = m["off_apres"]["profils"]
    ok0 = (len(profs) == 3 and profs[0] == "Psychic" and profs[1] == "Psychic"
           and profs[2] not in (None, "Psychic"))
    add("[523r1] VERDICT-0 profils des attaques d'allie = %s (attendu Psychic/Psychic/non-Psychic)"
        " -> %s" % (profs, "OK" if ok0 else "MONTAGE KO"))
    rc |= 0 if ok0 else 1

    # --- VERDICT-1 : le COMPTEUR avance de 1 par attaque PSYCHIQUE, et de 0 sur le temoin ---------
    live_mti = [a.get("mti") for a in m["att_live"]]
    for i, t in enumerate(m["off_apres"]["trace"]):
        add("[523r1]   offline %-24s profil=%-10s compteur=%s  mti offline=%s live=%s"
            % (t["etape"], t.get("profil"), t["compteur"], t.get("mti"),
               (live_mti[i - 1] if 0 < i <= len(live_mti) else None)))
    suite = [(t["compteur"] or 0) for t in m["off_apres"]["trace"]]
    ok1 = suite == [0, 1, 2, 2]
    add("[523r1] VERDICT-1 suite du compteur = %s (attendu [0, 1, 2, 2]) -> %s"
        % (suite, "OK" if ok1 else "ECART"))
    rc |= 0 if ok1 else 1

    # --- VERDICT-2 : `GetNumTotalHits` = nrOfHits + min(compteur, maxNrOfHits - nrOfHits) ---------
    nr, mx = m["nr_of_hits"], m["max_nr_of_hits"]
    att = nr + min(m["off_apres"]["compteur_avant_cast"] or 0, mx - nr)
    ok2 = (m["off_base"]["hits"] == nr) and (m["off_apres"]["hits"] == att)
    add("[523r1] VERDICT-2 GetNumTotalHits : nrOfHits=%s maxNrOfHits=%s ; base=%s (attendu %s) "
        "apres=%s (attendu %s) -> %s"
        % (nr, mx, m["off_base"]["hits"], nr, m["off_apres"]["hits"], att,
           "OK" if ok2 else "MISMATCH"))
    rc |= 0 if ok2 else 1

    # --- VERDICT-3 : NOMBRE de coups APPLIQUES, offline vs LIVE, tour 1 puis tour 2 --------------
    # C'EST L'OBSERVABLE DE LA TRANCHE. La MAGNITUDE par coup fait l'objet du verdict 6, separement :
    # elle depend de l'ALIGNEMENT du PRNG, que le prelude d'attaques peut rompre.
    add("[523r1] LIVE tour 1 ok=%s errors=%s ; per-coup : %s"
        % (m["live1_ok"], m["live1_err"],
           json.dumps({str(k): v for k, v in sorted(m["live1"].items())})))
    l1 = m["live1"].get(m["target"]) or []
    o1 = m["off_apres"]["per_hit"].get(m["target"]) or []
    ok3a = len(o1) == len(l1) and len(l1) > 0
    add("[523r1] VERDICT-3a tour 1 NB de coups offline=%s live=%s -> %s"
        % (len(o1), len(l1), "OK" if ok3a else "ECART"))
    rc |= 0 if ok3a else 1

    t2 = m["tour2"]
    if t2["off"] is None:
        add("[523r1] VERDICT-3b NON EXERCE : au tour 2 la cible u%s n'est plus legale fromHere "
            "(legal=%s, caster@%s cible@%s, repositionnement=%s)"
            % (m["target"], t2["legal"], t2["caster_pos"], t2["target_pos"],
               t2.get("repositionne")))
        l2, o2 = [], []
        rc |= 1
    else:
        l2 = t2["live"].get(m["target"]) or []
        o2 = t2["off"]["per_hit"].get(m["target"]) or []
        ok3b = len(o2) == len(l2) and len(l2) > 0
        add("[523r1] VERDICT-3b tour 2 NB de coups offline=%s live=%s (caster@%s cible@%s, "
            "repositionnement=%s) -> %s"
            % (len(o2), len(l2), t2["caster_pos"], t2["target_pos"], t2.get("repositionne"),
               "OK" if ok3b else "ECART"))
        rc |= 0 if ok3b else 1

    # --- VERDICT-4 : LE REGIME EST-IL NON DEGENERE ? le delta doit etre > 0 des DEUX cotes -------
    if t2["off"] is None:
        add("[523r1] VERDICT-4 NON EXERCE : pas de 2e cast (cf. 3b) -- l'accord du tour 1 ne prouve "
            "alors RIEN sur la VARIATION du compteur")
        rc |= 1
    else:
        d_off = len(o1) - len(o2)
        d_live = len(l1) - len(l2)
        ok4 = (d_off == d_live) and d_off > 0
        add("[523r1] VERDICT-4 delta coups (tour 1 - tour 2) : offline=%s live=%s -> %s"
            % (d_off, d_live, "OK" if ok4 else ("DEGENERE" if d_off == 0 else "ECART")))
        rc |= 0 if ok4 else 1

    # --- VERDICT-5 : la branche `On(TurnEnd)` (OFFLINE, le seul cote falsifiable) ----------------
    te = m["turn_end"]
    ok5 = (te["avant"] == 2) and (te["apres"] is None) and (te["hits"] == nr)
    add("[523r1] VERDICT-5 On(TurnEnd) offline : compteur avant=%s apres=%s ; hits du cast suivant=%s"
        " (attendu 2 / None / %s) -> %s" % (te["avant"], te["apres"], te["hits"], nr,
                                            "OK" if ok5 else "ECART"))
    rc |= 0 if ok5 else 1

    # --- VERDICT-6 : la MAGNITUDE par coup -- exercee SEULEMENT si le PRNG est ALIGNE ------------
    # Le tour 1 a un PRELUDE (trois attaques d'allie) : chacune consomme des tirages, et rien ne
    # garantit que le port en consomme le MEME nombre que le natif. On MESURE l'alignement au lieu
    # de le supposer -- et quand il est rompu, comparer les degats reviendrait a accuser CETTE
    # tranche d'un ecart qui appartient au modele de degat des attaques du prelude.
    rl = m.get("rng_live_avant_cast") or {}
    ro = (m["off_apres"].get("rng_avant_cast") or {})
    aligne1 = bool(rl.get("mt")) and bool(ro.get("mt")) \
        and int(rl.get("mti", -1)) == int(ro.get("mti", -2)) \
        and list(rl["mt"]) == list(ro["mt"])
    add("[523r1] PRNG avant le cast du tour 1 : live mti=%s offline mti=%s ; etats identiques=%s"
        % (rl.get("mti"), ro.get("mti"), aligne1))
    if aligne1:
        ok6a = (len(o1) == len(l1) and all(int(a) == int(b) for a, b in zip(o1, l1)))
        add("[523r1] VERDICT-6a tour 1 per-coup offline=%s live=%s -> %s"
            % (o1, l1, "OK" if ok6a else "ECART"))
        rc |= 0 if ok6a else 1
    else:
        add("[523r1] VERDICT-6a NON EXERCE (tour 1) : PRNG DESALIGNE par le prelude d'attaques -- "
            "offline=%s live=%s, ecart de MAGNITUDE, pas de NOMBRE (cf. 3a)" % (o1, l1))
    if t2["off"] is not None:
        # Le tour 2 n'a AUCUN prelude : la capture est fraiche et le cast est la PREMIERE
        # consommation de PRNG des deux cotes -- la magnitude y est donc comparable. Critere = celui
        # de `probe_523` : la sequence LIVE est un PREFIXE de la sequence offline CLAMPEE par les PV,
        # dont la queue est NULLE (le natif cesse d'emettre sur un cadavre).
        hp0 = (t2["off"]["hp0"] or {}).get(m["target"], 0)
        oc2 = clamped(o2, hp0)
        ok6b = (len(oc2) >= len(l2) and len(l2) > 0
                and all(int(a) == int(b) for a, b in zip(oc2, l2))
                and all(int(x) == 0 for x in oc2[len(l2):]))
        add("[523r1] VERDICT-6b tour 2 per-coup (SANS prelude, PV cible=%s) offline(brut)=%s "
            "offline(clampe)=%s live=%s -> %s"
            % (hp0, o2, oc2, l2, "OK" if ok6b else "ECART"))
        rc |= 0 if ok6b else 1
    return rc, out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--rank", default="17")
    # PV HAUT sur tout le monde : ce probe compte des COUPS, pas des degats. Une cible qui meurt
    # arrete l'emission native (`UnitFlag.Overkilled`) et le compte de coups ne dirait plus rien.
    ap.add_argument("--hp", type=int, default=60000)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)

    tmp = ROOT / "logs" / "probe523r1"
    tmp.mkdir(parents=True, exist_ok=True)
    st_file = Path(args.state_file or (tmp / ("state-%s.json" % uuid.uuid4().hex[:8])))
    sid = _resolve_session()
    m = mesure(sid, st_file, seed=args.seed, board=args.board, rank=args.rank, hp=args.hp,
               keep=args.keep)
    rc, lignes = verdicts(m)
    print("\n".join(lignes))
    print("[523r1] rc=%s" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
