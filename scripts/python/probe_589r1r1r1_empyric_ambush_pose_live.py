#!/usr/bin/env python
"""probe #589-r1-r1-r1 -- CONFRONTATION de la POSE d'`EmpyricAmbush` (ability ACTIVE 1232).

CRITERE BINAIRE, pose avant toute methode :

    « Quand `eldarLhykhis` caste 1232, le PORT reproduit-il les TROIS observables du natif --
      la TUILE ou elle atterrit, la salve de degats par coup, et la marque 1578 posee sur la
      cible -- a partir du MEME etat et du MEME flux PRNG ? »

Avant #589-r1-r1-r1, `EmpyricAmbushAbility` etait absente d'`ABILITY_CLASSES` : le cast offline
etait un NO-OP COMPLET (aucun vol, aucun degat, aucune marque) et l'effet 1578 n'entrait dans
l'etat du port QUE par la capture live. C'est la contre-epreuve `NOPORT` ci-dessous.

## LE MONTAGE, et pourquoi chaque piece y est

  * `eldarLhykhis` est **HORS CATALOGUE** du seed BC (`catalog_inject --missing` la liste ;
    `rl_duel build --list-pool` ne la rend pas) -> `write_augmented_seed_bc` + `--seed-bc`.
  * L'ANCRE de la cible est choisie BIEN ENTOUREE (>= 5 voisins marchables) : sans plusieurs
    tuiles libres au contact, `First(SortTilesByUtility(Randomize(...)))` n'a qu'un candidat et
    la tuile d'atterrissage cesse de discriminer quoi que ce soit (le `Randomize` ne tirerait
    qu'une fois, sur un pool de 1).
  * Lhykhis part a distance >= 3 de l'ancre : le vol doit etre un VRAI deplacement, sinon
    « le port n'a pas bouge » et « le port a bouge au bon endroit » rendent le meme etat.
  * `--crit 0,0` : aucun coup ne crite des DEUX cotes, donc la salve est le pipeline de degat NU
    (pas de canal crit qui viendrait masquer un ecart de bornes ou de nombre de coups).
    Le canal crit de l'effet 1578, lui, est deja confronte par `probe_589r1r1_empyric_ambush_live`.
  * PV gonfles : la cible ne doit pas mourir pendant les `nrOfHits` = 8 coups (un cadavre change
    la geometrie ET tronque le flux d'evenements).

## LES DEUX FACES, mesurees SEPAREMENT

  * DECIDER -- le RPC `abilityTargets` rend l'ensemble des cibles que le NATIF accepte pour 1232 ;
    le port le rejoue par `get_invalid_target_reason` sur CHAQUE unite du board. Les deux
    ensembles doivent coincider. C'est le masque `0x6004020` qui est en jeu, en particulier
    `TargetHasFreeAdjacentTile` (bit 5) -- un ennemi ENCERCLE doit etre REFUSE des deux cotes.
  * EXECUTER -- le cast lui-meme (vol + salve + marque), rejoue offline sur le snapshot pris
    JUSTE AVANT, RNG cale sur le dump du meme instant.

## CE QUE LE CARRE PROUVE

Pour chaque observable, deux confrontations independantes :
  1. LIVE == OFFLINE (le port reproduit le natif) ;
  2. MUTATION `NOPORT` (1232 retiree d'`ABILITY_CLASSES` -> le handler retombe sur
     `ported: False`, behaviour no-op) : le rejeu doit CHANGER sur les TROIS observables.
Sans le point 2, « ca concorde » ne vaudrait rien.

Usage :
    python probe_589r1r1r1_empyric_ambush_pose_live.py
    python probe_589r1r1r1_empyric_ambush_pose_live.py --board C1_74 --seed 31337
    python probe_589r1r1r1_empyric_ambush_pose_live.py --encercle     # bras DECISION seul
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

CARRIER = "eldarLhykhis"          # porteur de l'ability active 1232 (HORS CATALOGUE -> --seed-bc)
ALLY = "blackHaarken"             # 2e unite de mon camp : elle NE caste pas, elle occupe le roster
ABILITY_TYPE = 1232               # ActiveAbilityType 0x4d0
EFFECT_NAME = "EmpyricAmbush"     # cle EFFECT_CLASSES == decisionView.units[].effects[].name
TR_TARGET_HAS_FREE_ADJACENT_TILE = 1 << 5   # `TargetingRule.TargetHasFreeAdjacentTile` = 0x20


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def seed_bc_avec_lhykhis() -> str:
    """`eldarLhykhis` n'est pas au catalogue du seed BC -> injection (jamais un deepcopy a la main,
    qui ne poserait que `BC.Units` et fauterait au cast, cf. runner.md)."""
    import catalog_inject
    fd, out = tempfile.mkstemp(prefix="probe_589r1r1r1_bc_", suffix=".json")
    os.close(fd)
    catalog_inject.write_augmented_seed_bc(out, [CARRIER])
    return out


def build(a, tag, seed_bc):
    fd, sf = tempfile.mkstemp(prefix="probe_589r1r1r1_%s_" % tag, suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--seed-bc", seed_bc,
            "--p-units", "%s,%s" % (CARRIER, ALLY),
            "--a-units", "%s,%s" % (a.target_unit, a.other_unit),
            "--hp-target", "900000", "--hp-player", "900000",
            "--no-ai", "--crit", a.crit, "--block-target", "0,0"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (tag, (p.stderr or p.stdout or "")[-600:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _pos_of(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def stage(h, a):
    """Place les unites et rend `(rec, raison)` -- `raison is None` == regime ATTEINT.

    ORDRE : placements -> `reach_my_turn(force_cycle=True)` (purge des flags et compteurs de tour)
    -> snapshot + dump RNG -> cast. Le snapshot est pris AVANT le cast : c'est lui que le rejeu
    offline consomme."""
    import hexgeo
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    if me is None:
        return None, "porteur %s absent du deploiement" % CARRIER
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if not ens:
        return None, "aucun ennemi"
    tgt = ens[0]

    occupe = {p for p in (_pos_of(u) for u in h.alive(dv)) if p is not None}
    marchables = [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]
    libres = [c for c in marchables if c not in occupe]

    def _n_voisins(c):
        return sum(1 for s in marchables if hexgeo.distance(s, c) == 1)

    # ANCRE bien entouree : il faut >= 3 tuiles LIBRES au contact pour que le pool de
    # `CanAddUnit(AdjacentTiles(cible))` ait de quoi departager (sinon `Randomize` est vacu).
    plan = None
    for anchor in sorted(libres, key=lambda c: (-_n_voisins(c), c)):
        if _n_voisins(anchor) < 5:
            break                                     # trie decroissant : plus rien de mieux ensuite
        contacts = [s for s in libres if hexgeo.distance(s, anchor) == 1]
        loin = [s for s in libres if hexgeo.distance(s, anchor) >= 3]
        if len(contacts) >= 3 and len(loin) >= 2:
            plan = (anchor, loin)
            break
    if plan is None:
        return None, "geometrie non realisable (aucune ancre a >= 5 voisins et 3 contacts libres)"
    anchor, loin = plan

    if not h.place(tgt["id"], anchor):
        return None, "placement de la cible refuse"
    for i, other in enumerate(ens[1:]):
        h.place(other["id"], loin[-(i + 1)])
    if not h.place(me["id"], loin[0]):
        return None, "placement de Lhykhis refuse"
    ally = h.by_visual(ALLY)
    if ally is not None:
        h.place(ally["id"], loin[1])

    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    tgt = next((u for u in h.enemies_of(h.my_player, dv) if u["id"] == tgt["id"]), None)
    if me is None or tgt is None:
        return None, "une unite a disparu apres le cycle de tour"

    rec = {"caster": me["id"], "target": tgt["id"], "step_to": None,
           "anchor": anchor, "caster_pos_avant": _pos_of(me),
           "contacts_libres": sorted(s for s in libres if hexgeo.distance(s, anchor) == 1)}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    if a.verbose:
        print("    Lhykhis en %s, cible en %s, contacts libres %s"
              % (rec["caster_pos_avant"], anchor, rec["contacts_libres"]))
    return rec, None


def stage_encercle(h, a):
    """BRAS `--encercle` : la cible est posee sur une tuile dont TOUS les voisins marchables sont
    OCCUPES. Le bit 5 du masque (`TargetHasFreeAdjacentTile`, 0x20) doit alors REFUSER le cast --
    des DEUX cotes. C'est le seul bras qui exerce ce bit : sans lui, le masque 0x6004020 serait
    valide a `TargetIsEnemy` pres, et le bit 5 pourrait etre faux sans que rien ne le dise.

    On DEPLACE les unites pour obtenir la configuration voulue (jamais « bloque par la geometrie de
    spawn ») : on cherche l'ancre marchable au MOINS de voisins marchables, et on bouche avec les
    unites restantes."""
    import hexgeo
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    if me is None:
        return None, "porteur %s absent du deploiement" % CARRIER
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    amis = [u for u in h.alive(dv) if u.get("owner") == h.my_player and u["id"] != me["id"]]
    if not ens:
        return None, "aucun ennemi"
    tgt = ens[0]
    boucheurs = [u["id"] for u in (amis + ens[1:])]

    marchables = [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]

    def _voisins(c):
        return [s for s in marchables if hexgeo.distance(s, c) == 1]

    # L'ancre doit avoir ASSEZ PEU de voisins marchables pour qu'on puisse tous les boucher, et
    # laisser une tuile a >= 2 pour Lhykhis (qui ne doit pas etre l'un des boucheurs).
    cand = sorted(((len(_voisins(c)), c) for c in marchables), key=lambda x: (x[0], x[1]))
    plan = None
    for n, anchor in cand:
        if n == 0 or n > len(boucheurs):
            continue
        loin = [s for s in marchables if hexgeo.distance(s, anchor) >= 2]
        if loin:
            plan = (anchor, _voisins(anchor), loin)
            break
    if plan is None:
        return None, ("aucune ancre encerclable avec %d boucheurs (min voisins = %d)"
                      % (len(boucheurs), cand[0][0] if cand else -1))
    anchor, voisins, loin = plan
    # PLAN de placement complet, puis 3 PASSES : un `place` echoue si la destination est encore
    # occupee A CET INSTANT, et la case peut se liberer au tour suivant de la boucle. Sans les
    # passes, l'ordre des unites deciderait du succes du montage.
    plan_pos = [(me["id"], None)] + [(tgt["id"], anchor)] + list(zip(boucheurs, voisins))
    for _ in range(3):
        reste = []
        occupe = {p for p in (_pos_of(u) for u in h.alive()) if p is not None}
        for uid, dest in plan_pos:
            if dest is None:                            # Lhykhis : 1re tuile LOINTAINE encore libre
                dest = next((s for s in loin if s not in occupe), None)
                if dest is None:
                    return None, "aucune tuile libre a distance >= 2 pour Lhykhis"
            if _pos_of(next((u for u in h.alive() if u["id"] == uid), None)) == dest:
                continue
            if h.place(uid, dest):
                occupe.add(dest)
            else:
                reste.append((uid, dest))
        plan_pos = reste
        if not plan_pos:
            break
    if plan_pos:
        return None, "placements non realises : %s" % plan_pos
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    tgt = next((u for u in h.alive(dv) if u["id"] == tgt["id"]), None)
    if me is None or tgt is None:
        return None, "une unite a disparu apres le cycle de tour"
    occupe = {p for p in (_pos_of(u) for u in h.alive(dv)) if p is not None}
    restants = [v for v in voisins if v not in occupe]
    if restants:
        return None, "encerclement INCOMPLET : %s encore libre(s) -- le bras ne prouve rien" % restants
    rec = {"caster": me["id"], "target": tgt["id"], "step_to": None, "anchor": anchor,
           "voisins": voisins}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    if a.verbose:
        print("    cible ENCERCLEE en %s (%d voisins marchables, tous occupes)"
              % (anchor, len(voisins)))
    return rec, None


def cast_live(h, rec):
    """Le CAST natif. Rend `(observables, raison)` : tuile d'atterrissage, salve par coup,
    presence de la marque sur la cible."""
    res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": ABILITY_TYPE}}, 60)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    if not a0.get("ok"):
        return None, "cast refuse : %s" % str(res)[:300]
    hits = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if ("Amount" in td and td.get("Attacker_Id") == rec["caster"]
                and td.get("Target_Id") == rec["target"]):
            hits.append(int(td["Amount"]))
    dv = h.dview()
    me = next((u for u in (dv.get("units") or []) if u.get("id") == rec["caster"]), None)
    tu = next((u for u in (dv.get("units") or []) if u.get("id") == rec["target"]), None)
    marks = [e.get("name") for e in ((tu or {}).get("effects") or [])]
    return {"landing": _pos_of(me), "hits": hits, "marked": EFFECT_NAME in marks,
            "effects": marks}, None


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE du MEME cast, RNG neutralise par le dump pris juste avant.

    DEUX MUTATIONS, et elles ne disent pas la meme chose :

      * `NOPORT` -- 1232 retiree d'`ABILITY_CLASSES` : le registre du handler est ce qui materialise
        l'ability, donc le retrait fait retomber `visit_ActiveAbilityMessage` sur `ported: False`
        (behaviour no-op COMPLET). C'est la vue « d'avant ce port » : ni vol, ni degat, ni marque.
      * `NORANDOM` -- le noeud `Randomize` remplace par l'IDENTITE dans l'arbre. Il repond a la
        seule question que `NOPORT` ne peut pas poser : **cet etage mord-il ?** Si la tuile
        d'atterrissage ne bougeait pas sans lui, l'accord sur le landing ne prouverait rien du
        tirage (regime degenere : utilites toutes distinctes, ou pool de 1). Le natif tire
        `len(pool)` fois DANS `FlyUnit`, donc la mutation decale aussi le flux des degats -- ce
        qu'on lit ici est le LANDING.

    Restaurees en `finally`."""
    from engine.runner.abilities import aeldari as _aeldari
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.components import PositionComponent
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    saved = ABILITY_CLASSES.get(ABILITY_TYPE)
    saved_rand = _aeldari.Randomize
    try:
        if mutate == "NOPORT":
            ABILITY_CLASSES.pop(ABILITY_TYPE, None)
        elif mutate == "NORANDOM":
            _aeldari.Randomize = lambda src: src            # l'etage de tirage COURT-CIRCUITE
        st = h.offline_state(rec)
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=rec["caster"], target_id=rec["target"],
                                          ability_type=ABILITY_TYPE))
        last = runner.ability_handler.last or {}
        e = st.get_entity(rec["caster"])
        pc = e.get_component(PositionComponent) if e is not None else None
        landing = (pc.col, pc.row) if pc is not None else None
        atk = last.get("attack") or {}
        hits = [int(x) for x in (atk.get("per_hit") or [])]
        marked = any(int(getattr(ef, "effect_type", -1)) == 1578
                     for ef in (st.effects.by_unit.get(rec["target"]) or []))
        return {"landing": landing, "hits": hits, "marked": marked,
                "ported": last.get("ported")}
    finally:
        if saved is not None:
            ABILITY_CLASSES[ABILITY_TYPE] = saved
        _aeldari.Randomize = saved_rand


def face_decision(h, rec):
    """FACE DECIDER, sur l'etat FIGE d'avant le cast. ORACLE = `abilityReason`, qui rend le masque
    `TargetingRule` NATIF par cible (`targetReason.hex`) -- pas un booleen : c'est lui qui dit POUR
    QUELLE REGLE le natif refuse. Le port le rejoue par `is_invalid_target`.

    CONTRAT DE FIDELITE (le meme que `test_ability_target_gate_live.py`) :

        natif == 0   =>  port == 0                 (STRICT : le port n'invente aucun refus)
        natif != 0   =>  port == natif             (regle PORTEE)
                     ou  port == 0                 (regle NON PORTEE -> permissif)
        jamais       :   port != 0 et port != natif (refus pour la MAUVAISE raison)

    C'est le masque `0x6004020` qui est en jeu -- `TargetIsEnemy` (bit 14) et surtout
    `TargetHasFreeAdjacentTile` (bit 5), le pendant DECISION du `CanAddUnit(AdjacentTiles(cible))`
    du behaviour."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import is_invalid_target
    st = h.offline_state(rec)
    ability = ABILITY_CLASSES[ABILITY_TYPE]()
    rows, fautes, vus = [], [], 0
    for u in h.alive():
        uid = int(u["id"])
        if uid == rec["caster"] or st.get_entity(uid) is None:
            continue
        r = h.rpc("abilityReason", {"runnerId": h.rid, "casterId": rec["caster"],
                                    "abilityType": ABILITY_TYPE, "targetId": uid}, 60) or {}
        tr = (r.get("targetReason") or {})
        if tr.get("hex") is None:
            return None, "abilityReason sans targetReason.hex pour %d : %s" % (uid, str(r)[:200])
        natif = int(tr["hex"], 16)
        port = int(is_invalid_target(st, rec["caster"], uid, ability))
        vus += 1
        rows.append((uid, natif, port, list(tr.get("reasons") or [])))
        if natif == 0 and port != 0:
            fautes.append("unite %d : natif ACCEPTE, port refuse 0x%x" % (uid, port))
        elif natif != 0 and port not in (0, natif):
            fautes.append("unite %d : natif 0x%x, port 0x%x (mauvaise raison)" % (uid, natif, port))
    if vus == 0:
        return None, "aucune cible confrontee (l'etat fige n'expose aucune autre unite)"
    return {"rows": rows, "fautes": fautes}, None


def run(a, rpc, Board, Harness, seed_bc) -> int:
    rid, sf = build(a, "pose", seed_bc)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = (stage_encercle(h, a) if a.encercle else stage(h, a))
        if rec is None:
            print("REFUS (montage) : %s" % why)
            return 2

        dec, why = face_decision(h, rec)
        rc = 0
        if a.encercle:
            # BRAS ENCERCLE : la seule chose qui compte est le VERDICT sur la cible encerclee.
            # Le natif DOIT rompre `TargetHasFreeAdjacentTile` (0x20) -- s'il ne le fait pas, le
            # montage n'a pas atteint son regime et le bras ne prouve rien.
            if dec is None:
                print("FACE DECIDER : NON MESUREE -- %s" % why)
                return 2
            ligne = next((r for r in dec["rows"] if r[0] == rec["target"]), None)
            if ligne is None:
                print("REFUS : la cible encerclee n'a pas ete confrontee")
                return 2
            uid, natif, port, noms = ligne
            print("[ENCERCLE] cible %d natif=0x%x %s | port=0x%x" % (uid, natif, noms, port))
            if not (natif & int(TR_TARGET_HAS_FREE_ADJACENT_TILE)):
                print("REFUS : le natif n'a PAS rompu TargetHasFreeAdjacentTile -- regime non atteint")
                return 2
            if port != natif:
                print("[ENCERCLE] FAUTE : port=0x%x != natif=0x%x" % (port, natif))
                return 1
            for f in dec["fautes"]:
                print("[ENCERCLE] FAUTE : %s" % f)
            return 1 if dec["fautes"] else 0
        if dec is None:
            print("FACE DECIDER : NON MESUREE -- %s" % why)
            rc |= 2
        else:
            for uid, natif, port, noms in dec["rows"]:
                print("[DECIDER] cible %-4d natif=0x%-8x port=0x%-8x %s"
                      % (uid, natif, port, noms))
            for f in dec["fautes"]:
                print("[DECIDER] FAUTE : %s" % f)
            if dec["fautes"]:
                rc |= 1

        live, why = cast_live(h, rec)
        if live is None:
            print("REFUS (cast live) : %s" % why)
            return rc | 2
        off = replay(h, rec)
        mut = replay(h, rec, mutate="NOPORT")
        nrd = replay(h, rec, mutate="NORANDOM")

        k = len(live["hits"])
        accord_landing = live["landing"] == off["landing"]
        accord_hits = live["hits"] == off["hits"][:k] and len(off["hits"]) == k
        accord_mark = bool(live["marked"]) == bool(off["marked"])
        # La MUTATION doit mordre sur les TROIS observables : sans elle l'accord ne prouve rien.
        mord = (mut["landing"] != off["landing"] and not mut["hits"] and not mut["marked"])
        # Et l'etage de TIRAGE doit mordre a son tour, sinon le landing ne prouve rien de lui.
        mord_rng = (nrd["landing"] != off["landing"] or nrd["hits"] != off["hits"])

        print("[EXECUTER] LIVE     landing=%s marked=%s hits=%s"
              % (live["landing"], live["marked"], live["hits"]))
        print("           OFFLINE  landing=%s marked=%s hits=%s (ported=%s)"
              % (off["landing"], off["marked"], off["hits"], off["ported"]))
        print("           NOPORT   landing=%s marked=%s hits=%s -> mord=%s"
              % (mut["landing"], mut["marked"], mut["hits"], mord))
        print("           NORANDOM landing=%s hits=%s -> mord=%s"
              % (nrd["landing"], nrd["hits"], mord_rng))
        print("           accord : landing=%s hits=%s mark=%s"
              % (accord_landing, accord_hits, accord_mark))
        if not (accord_landing and accord_hits and accord_mark):
            rc |= 1
        if not mord:
            rc |= 1
        if not mord_rng:
            print("           /!\\ NORANDOM n'a rien change : cet etage n'est PAS exerce ici")
            rc |= 1
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--crit", default="0,0",
                    help="CritChance,CritDamage des p-units. 0 = salve NUE (aucun canal crit).")
    ap.add_argument("--target-unit", default="necroWarden")
    ap.add_argument("--other-unit", default="necroOverlord")
    ap.add_argument("--encercle", action="store_true",
                    help="BRAS DECISION : la cible est ENCERCLEE (aucune tuile libre au contact). "
                         "Le bit 5 du masque (TargetHasFreeAdjacentTile) doit REFUSER le cast des "
                         "DEUX cotes -- c'est le seul bras qui l'exerce.")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    print("== #589-r1-r1-r1 EmpyricAmbush POSE (ability 1232) -- board %s seed %s"
          % (a.board, a.seed))

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    seed_bc = seed_bc_avec_lhykhis()
    try:
        rc = run(a, rpc, Board, ChargeRegimeHarness, seed_bc)
    finally:
        Path(seed_bc).unlink(missing_ok=True)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
