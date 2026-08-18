#!/usr/bin/env python
"""probe #951-r4 -- CONFRONTATION du `ownerNeedsToBeAlive: true` de `FireOfAbsolution`.

CRITERE BINAIRE, pose avant toute methode :

    << Quand `adeptRetributor` (<< Vindicta >>) est TUE PAR UNE RIPOSTE pendant sa propre attaque
       normale a distance, le natif applique-t-il quand meme le splash de `FireOfAbsolution` aux
       voisins de sa cible -- et le PORT rend-il le MEME verdict ? >>

L'observable est le DELTA DE PV des unites ADJACENTES a la cible, qui ne peuvent etre touchees que
par le splash (`AdjacentUnits(target) - caster - target`).

## CE QUE CE PROBE A ETABLI, ET IL TRANCHE DANS LES DEUX SENS

`#951-r4` demandait de PORTER le `ownerNeedsToBeAlive: true` du `CreateTrigger`, en declarant le
gate << inobservable sur ce vecteur, l'attaquant etant vivant par construction d'une attaque qu'il
vient de porter >>. La CONCLUSION tient, la RAISON est fausse, et le port aurait DEGRADE :

  1. **Le natif applique le splash MEME quand l'attaquant meurt de la riposte.** Flux releve coup
     par coup (`--verbose`), `MC1_67`/777, Vindicta a 2000 PV face a `darkaHellblaster` :

        coups 00-03  arme      83 -> 77   (4 coups Flame)
        coups 04-06  SPLASH    83 -> 79   FireOfAbsolution
        coups 07-09  SPLASH    83 -> 81   FireOfAbsolution
        coup  10     RIPOSTE   77 -> 83   -- Vindicta MEURT ICI, en DERNIER

     `ExecuteAtomic(this, b, entities, 0x3d)` enveloppe `GetAttackDamageBehaviour` ET
     `EvaluateAbilities(0x4a)` : les abilities declenchees par `On(9)` sont mises en FILE et jouees
     a la SORTIE du groupe. L'owner est donc VIVANT quand `On(0x4a)` part -- toujours, et pas
     << parce qu'il vient de frapper >>.
  2. **Le port, lui, joue la riposte AVANT ce vecteur** (elle est dans
     `AttackDamageOperation.execute`), donc son attaquant est deja mort au splash. Mesure sur le
     MEME montage : splash NATIF **18 714**, port **14 970** (-20 %, une perte de membre
     d'escouade) -- une divergence de RANG, PREEXISTANTE (residu `#951-r9`).
  3. **Poser le gate mettrait le splash du port a ZERO** : la mutation `WITHGATE` le fait, et c'est
     la contre-epreuve de ce probe. Le gate transformerait une divergence de 20 % en no-op complet.

## LE MONTAGE, et pourquoi chaque piece y est

  * Sarquael est le DEFENSEUR : c'est lui qui riposte. Ses deux allies sont poses ADJACENTS a lui --
    ce sont EUX les temoins du splash, et ils ne peuvent pas armer/desarmer sa riposte (le gate
    `GrimRetribution` compte les ennemis adjacents a SARQUAEL, c.-a-d. MES unites).
  * Vindicta est posee a distance `--dist` (>= 2) : Sarquael doit n'avoir AUCUN ennemi adjacent,
    sinon sa riposte est desarmee et le bras REGIME ne se produit pas.
  * `--unit-stat adeptRetributor:Health=<bas>` : c'est la SEULE difference entre les deux bras.
  * `--crit 0,0` / `--block-target 0,0` : aucun canal aleatoire ne decide de la mort.

## LES DEUX BRAS, et pourquoi il en faut DEUX

  * `REGIME` (defaut) -- Vindicta MEURT de la riposte. Le natif applique QUAND MEME le splash, et le
    port doit en appliquer un NON NUL. C'est le cliquet : quiconque poserait le gate le fait rougir.
  * `--survivant` -- MEME montage, MEME attaque, MEME cible, PV de Vindicta hors d'atteinte : elle
    survit. Splash NATIF == PORT, BIT-EXACT (22 458 mesure). Sans ce bras, l'accord du bras REGIME
    ne dirait pas si le port sait faire le splash du tout.

La contre-epreuve `WITHGATE` POSE le gate absent : elle doit ramener le splash offline a ZERO.
C'est elle qui etablit que l'absence de gate est une DECISION mesuree, pas un oubli.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_951r4_fire_of_absolution_owner_alive.py
    python probe_951r4_fire_of_absolution_owner_alive.py --survivant
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

CARRIER = "adeptRetributor"        # << Vindicta >>, passif `FireOfAbsolution`
ALLY = "blackHaarken"              # 2e unite de mon camp : elle n'agit pas, elle est garee loin
DEFENDER = "darkaHellblaster"      # << Sarquael >>, passif `GrimRetribution` (riposte sur On(9))


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _pos_of(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def build(a):
    fd, sf = tempfile.mkstemp(prefix="probe_951r4_", suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--p-units", "%s,%s" % (CARRIER, ALLY),
            "--a-units", "%s,%s,%s" % (a.defender, a.voisin1, a.voisin2),
            "--hp-target", str(a.hp_target),
            "--hp-player", str(a.hp_survivant if a.survivant else a.hp_carrier),
            "--no-ai", "--crit", "0,0", "--crit-target", "0,0",
            "--block-target", "0,0", "--block-player", "0,0"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("build KO : %s" % ((p.stderr or p.stdout or "")[-900:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _hp_live(ob, unit_id):
    """PV et etat de mort d'une unite dans `observeBattle`.

    ⚠ `observeBattle.units[]` N'A PAS de cle `id` : le projecteur publie `entityId` (le PIED) et
    `squadId` (l'ESCOUADE), et c'est le `squadId` qui correspond a `decisionView.units[].id`, donc a
    l'id d'entite du port. Un lecteur qui interroge `u["id"]` n'apparie RIEN et rend `None` --
    silencieusement."""
    for u in (ob.get("units") or []):
        if u.get("squadId") == unit_id or u.get("entityId") == unit_id:
            return u.get("hp"), bool(u.get("isDead"))
    return None, None


def _hp_port(st, unit_id):
    from engine.runner.components import HealthComponent, UnitComponent
    e = st.get_entity(int(unit_id))
    if e is None:
        return None, None
    hc = e.get_component(HealthComponent)
    uc = e.get_component(UnitComponent)
    return (None if hc is None else int(hc.hp)), (None if uc is None else (not uc.alive))


def stage(h, a):
    """Monte le regime et rend `(rec, raison)`. `raison is None` == regime ATTEINT."""
    import hexgeo
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    if me is None:
        return None, "porteur %s absent du deploiement" % CARRIER
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    defe = next((u for u in ens if u.get("visualId") == a.defender), None)
    if defe is None:
        return None, "defenseur %s absent du deploiement" % a.defender
    voisins = [u for u in ens if u["id"] != defe["id"]]
    if len(voisins) < 2:
        return None, "il faut 2 allies du defenseur (les temoins du splash) -- %d" % len(voisins)
    allie = next((u for u in h.alive(dv)
                  if u.get("owner") == h.my_player and u["id"] != me["id"]), None)

    marchables = [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]

    # ⚠ VINDICTA NE BOUGE PAS, ET C'EST LOAD-BEARING (mesure). Le defenseur porte le trait
    # `Overwatch` : tout pas de Vindicta a sa portee declenche un tir d'overwatch, qui TUE un
    # porteur a PV reduits -- c'est-a-dire exactement le bras REGIME. Symptome mesure : `place`
    # rendait `False` sur 8 tuiles differentes (l'unite n'etait plus dans `alive()`), et le montage
    # se lisait << geometrie non realisable >>. On ANCRE donc sur la position COURANTE de Vindicta
    # et on amene les autres autour d'elle -- aucune de celles-la ne porte `Overwatch`.
    poste = _pos_of(me)
    if poste is None:
        return None, "Vindicta n'a pas de position"

    def _plans():
        """⚠ GEOMETRIE CONTRAINTE PAR UNE MESURE, pas par confort. Les deux temoins du splash sont
        ADJACENTS a la cible ; s'ils sont AUSSI adjacents a Vindicta, le natif la declare ENGAGEE et
        `abilityTargets` ne lui laisse qu'EUX comme cibles -- l'`applyAction` sur la vraie cible est
        alors refuse EN SILENCE (mesure : `targets` = [le seul voisin adjacent], la cible absente).
        Les contacts sont donc choisis a distance >= 2 de Vindicta.

        Les tuiles libres sont RE-LUES a chaque tentative : un `place` est un vrai
        `MoveUnitOperation` et peut ECHOUER (pas de chemin, tuile devenue occupee) -- une liste
        figee ferait rendre << geometrie non realisable >> pour un plan simplement perime."""
        occupe = {p for p in (_pos_of(u) for u in h.alive()) if p is not None}
        libres = [c for c in marchables if c not in occupe or c == poste]
        for anchor in sorted(c for c in libres
                             if c != poste and hexgeo.distance(c, poste) == a.dist):
            contacts = [s for s in libres
                        if s != poste and hexgeo.distance(s, anchor) == 1
                        and hexgeo.distance(s, poste) >= 2]
            garages = [s for s in libres
                       if hexgeo.distance(s, anchor) >= 6 and hexgeo.distance(s, poste) >= 2]
            if len(contacts) >= 2 and garages:
                yield (anchor, contacts[:2], garages[0])

    echecs = []
    for _essai in range(a.essais):
        plan = next(iter(_plans()), None)
        if plan is None:
            return None, ("geometrie non realisable (2 contacts NON adjacents a Vindicta autour "
                          "d'une ancre a distance %d + un garage) -- echecs: %s" % (a.dist, echecs))
        anchor, contacts, garage = plan
        # ⚠ ORDRE : le GARAGE de mon allie d'abord (il ne doit jamais etre adjacent a Sarquael,
        # sinon il DESARME la riposte -- le gate `GrimRetribution` est
        # `AmountIsZero(AdjacentEnemies(Owner))`), puis les deux temoins, puis le DEFENSEUR.
        if allie is not None and not h.place(allie["id"], garage):
            echecs.append(("allie", garage))
            continue
        if not all(h.place(u["id"], c) for u, c in zip(voisins, contacts)):
            echecs.append(("temoins", contacts))
            continue
        if not h.place(defe["id"], anchor):
            echecs.append(("defenseur", anchor))
            continue
        break
    else:
        return None, "aucun plan tenable en %d essais -- echecs: %s" % (a.essais, echecs)

    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"

    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    if me is None:
        return None, "Vindicta n'est plus sur le plateau apres le cycle de tour"
    ob = h.rpc("observeBattle", {"runnerId": h.rid}, 40) or {}
    hp_me, mort_me = _hp_live(ob, me["id"])
    if mort_me:
        return None, "Vindicta est morte AVANT l'attaque (hp=%s)" % hp_me
    # Le gate de la riposte se VERIFIE, il ne se suppose pas : aucune de MES unites adjacente au
    # defenseur.
    pos_def = _pos_of(next(u for u in h.alive(dv) if u["id"] == defe["id"]))
    for u in h.alive(dv):
        if u.get("owner") == h.my_player and hexgeo.distance(_pos_of(u), pos_def) == 1:
            return None, "une de mes unites est ADJACENTE au defenseur -- la riposte est desarmee"

    nat = h.normal_attack_type(me["id"], dv)
    if nat is None:
        return None, "attaque normale introuvable pour Vindicta"
    # ⚠ ON DEMANDE AU JEU, on ne suppose pas la portee : `abilityTargets` rend les cibles que le
    # natif accepte pour CETTE ability depuis CETTE position. Un `applyAction` sur une cible
    # absente de cette liste rend `ok=True` et ne fait RIEN (signature #111).
    at = h.rpc("abilityTargets", {"runnerId": h.rid, "unitId": me["id"],
                                  "abilityType": int(nat)}, 40) or {}
    # Forme du retour : `units[].abilities[].targets[].targetId` (et `fromHere[]`, la legalite du
    # cast SANS bouger). On lit `fromHere` : le montage ne fait bouger personne.
    cibles = set()
    for u in (at.get("units") or []):
        if u.get("unitId") != me["id"]:
            continue
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId") or -1) != int(nat):
                continue
            for t in (ab.get("fromHere") or ab.get("targets") or []):
                cibles.add(t.get("targetId"))
    if a.verbose:
        print("    [ids] Vindicta=%s@%s cible=%s@%s voisins=%s"
              % (me["id"], _pos_of(me), defe["id"], pos_def,
                 [(u["id"], _pos_of(next(x for x in h.alive(dv) if x["id"] == u["id"])))
                  for u in voisins]))
        print("    [abilityTargets] nat=%s -> %s" % (nat, sorted(x for x in cibles
                                                                if x is not None)))
        print("    [abilityTargets brut] %s" % (str(at)[:700]))
    if cibles and defe["id"] not in cibles:
        return None, ("la cible n'est PAS dans `abilityTargets` a distance %d (cibles: %s) -- le "
                      "natif refuserait l'attaque EN SILENCE" % (a.dist, sorted(
                          x for x in cibles if x is not None)))
    rec = {"caster": me["id"], "target": defe["id"], "step_to": None, "ability_type": nat,
           "voisins": [u["id"] for u in voisins],
           "hp_avant": {u["id"]: _hp_live(ob, u["id"])[0] for u in voisins},
           "hp_caster_avant": hp_me, "hp_cible_avant": _hp_live(ob, defe["id"])[0]}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    return rec, None


def attaque_live(h, rec):
    res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": int(rec["ability_type"])}}, 60)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    if not a0.get("ok"):
        return None, "attaque normale refusee : %s" % str(res)[:300]
    ob = h.rpc("observeBattle", {"runnerId": h.rid}, 40) or {}
    hp_c, mort_c = _hp_live(ob, rec["caster"])
    return ({"caster_mort": mort_c, "hp_caster": hp_c,
             "hp_cible": _hp_live(ob, rec["target"])[0],
             "hp_apres": {v: _hp_live(ob, v)[0] for v in rec["voisins"]},
             "events": a0.get("events") or (res.get("events") if isinstance(res, dict) else None),
             "brut": res}, None)


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE de la MEME attaque normale, RNG cale sur le dump pris juste avant.

    MUTATION `WITHGATE` : on POSE le gate `ownerNeedsToBeAlive` que le port ne porte PAS -- c'est la
    contre-epreuve du verdict #951-r4, et elle doit RAMENER LE SPLASH A ZERO. C'est ce qui etablit
    que << ne pas le porter >> n'est pas un oubli mais une decision : le porter, sur ce port-ci,
    supprime un splash que le natif applique.

    ⚠ LA SUBSTITUTION VISE `dispatch.ability._fire_of_absolution_after_attack`, PAS
    `loki.fire._fire_of_absolution_after_attack`. Le site d'appel fait
    `from ..loki import _fire_of_absolution_after_attack` -- une liaison de FORME A, donc gelee au
    chargement : patcher le module SOURCE ne mordrait PAS, et la contre-epreuve comparerait le port
    a lui-meme (le faux vert que le CLAUDE.md decrit)."""
    from engine.runner.components import UnitComponent, unit_extensions_is_alive
    from engine.runner.operations.triggers.dispatch import ability as A
    saved = A._fire_of_absolution_after_attack
    try:
        if mutate == "WITHGATE":
            def _avec_gate(state, attacker_id, target_id, ranged, _o=saved):
                # `On(0x4a, ownerNeedsToBeAlive: 1)` = `EventTypeTrigger(0x4a) &
                # <DSLTriggers+0x20 = OwnerIsAliveAbilityTrigger>`, dont le corps est
                # `IsUnit(Owner) ? UnitExtensions$$IsAlive(owner, state) : true`.
                e = state.get_entity(attacker_id)
                if e is None or not unit_extensions_is_alive(e):
                    return []
                return _o(state, attacker_id, target_id, ranged)
            A._fire_of_absolution_after_attack = _avec_gate
        res = h.replay_offline(rec)
        st = res["state"]
        hp_c, mort_c = _hp_port(st, rec["caster"])
        return {"caster_mort": mort_c, "hp_caster": hp_c,
                "hp_cible": _hp_port(st, rec["target"])[0],
                "hp_apres": {v: _hp_port(st, v)[0] for v in rec["voisins"]},
                "per_hit": res.get("per_hit") or []}
    finally:
        A._fire_of_absolution_after_attack = saved


def _coups(events):
    """Les evenements de DEGAT du flux natif, dans l'ORDRE -- c'est lui qui dit si la riposte tombe
    AVANT ou APRES le splash, question que la seule somme des PV ne peut pas trancher."""
    out = []
    for e in (events or []):
        if e.get("kind") != "action":
            continue
        try:
            tags = json.loads(e.get("tags") or "{}")
        except Exception:
            continue
        if "Amount" in tags:
            out.append(tags)
    return out


def _splash(rec, obs):
    """Somme des PV perdus par les VOISINS de la cible -- le seul canal qui les atteigne est le
    splash de `FireOfAbsolution` (`AdjacentUnits(target) - caster - target`)."""
    tot = 0
    for v, avant in rec["hp_avant"].items():
        apres = (obs.get("hp_apres") or {}).get(v)
        if avant is None or apres is None:
            return None
        tot += int(avant) - int(apres)
    return tot


def mesurer(a, rpc, Board, Harness, rid) -> dict:
    """LA MESURE, sur un runner DEJA construit -- sans impression ni verdict."""
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
    bras = "SURVIVANT" if a.survivant else "REGIME (Vindicta meurt)"
    rec, why = stage(h, a)
    if rec is None:
        return {"ok": False, "why": "montage : %s" % why, "bras": bras}
    live, why = attaque_live(h, rec)
    if live is None:
        return {"ok": False, "why": "attaque live : %s" % why, "bras": bras}
    off = replay(h, rec)
    mut = replay(h, rec, mutate="WITHGATE")
    coups = _coups(live.get("events"))
    return {"ok": True, "why": None, "bras": bras,
            "mort_attendue": (not a.survivant),
            "rec": {k: rec[k] for k in ("caster", "target", "voisins", "hp_avant",
                                        "hp_caster_avant", "hp_cible_avant")},
            "live": live, "offline": off, "withgate": mut, "coups": coups,
            "ordre": _ordre_natif(rec, coups),
            "splash_live": _splash(rec, live), "splash_port": _splash(rec, off),
            "splash_withgate": _splash(rec, mut),
            "_h": h, "_rec": rec}


def _ordre_natif(rec, coups):
    """`{"splash": <rang du 1er coup de splash>, "riposte": <rang du 1er coup PORTE SUR le caster>}`.

    C'est l'etage qui tranche `#951-r4` : si la riposte tombe APRES le splash, l'owner est vivant
    quand `On(0x4a)` part, et le gate `ownerNeedsToBeAlive` ne peut PAS mordre sur ce vecteur."""
    vois, cast = set(rec["voisins"]), rec["caster"]
    splash = next((i for i, t in enumerate(coups) if t.get("Target_Id") in vois), None)
    riposte = next((i for i, t in enumerate(coups) if t.get("Target_Id") == cast), None)
    return {"splash": splash, "riposte": riposte}


def run(a, rpc, Board, Harness) -> int:
    rid, sf = build(a)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        m = mesurer(a, rpc, Board, Harness, rid)
        if not m.get("ok"):
            print("REFUS (%s)" % m.get("why"))
            return 2
        print("[%s] Vindicta hp avant = %s | cible hp avant = %s"
              % (m["bras"], m["rec"]["hp_caster_avant"], m["rec"]["hp_cible_avant"]))
        print("[%s] cible hp apres : LIVE %s | OFFLINE %s"
              % (m["bras"], m["live"].get("hp_cible"), m["offline"].get("hp_cible")))
        print("[%s] LIVE    : caster_mort=%s hp=%s | splash sur les voisins = %s"
              % (m["bras"], m["live"]["caster_mort"], m["live"]["hp_caster"], m["splash_live"]))
        print("[%s] OFFLINE : caster_mort=%s hp=%s | splash = %s"
              % (m["bras"], m["offline"]["caster_mort"], m["offline"]["hp_caster"],
                 m["splash_port"]))
        print("[%s] WITHGATE: splash = %s (contre-epreuve : le gate POSE)"
              % (m["bras"], m["splash_withgate"]))
        print("[%s] ordre natif : 1er coup de splash = #%s, 1er coup SUR le caster (riposte) = #%s"
              % (m["bras"], m["ordre"]["splash"], m["ordre"]["riposte"]))
        # DECOMPOSITION PAR CIBLE : une somme qui diverge ne dit pas OU. On imprime le detail
        # voisin par voisin, des trois cotes, avant tout verdict.
        for v in m["rec"]["voisins"]:
            av = m["rec"]["hp_avant"].get(v)
            print("    [voisin %s] avant %s | LIVE %s | PORT %s | WITHGATE %s"
                  % (v, av, (m["live"].get("hp_apres") or {}).get(v),
                     (m["offline"].get("hp_apres") or {}).get(v),
                     (m["withgate"].get("hp_apres") or {}).get(v)))
        if a.verbose:
            for i, t in enumerate(_coups(m["live"].get("events"))):
                print("    [coup %02d] att=%s -> tgt=%s amount=%s profil=%s ability=%s"
                      % (i, t.get("Attacker_Id"), t.get("Target_Id"), t.get("Amount"),
                         t.get("DamageProfileType"), t.get("Active_Ability_Type")))

        rc = 0
        # ⚠ L'ATTAQUE A-T-ELLE EU LIEU ? `applyAction` rend `ok=True` MEME quand le natif refuse en
        # silence (hors portee -- signature #111). Sans ce cran, un refus silencieux se lirait
        # << le natif n'applique pas le splash >>, c'est-a-dire exactement le verdict qu'on cherche.
        av, ap = m["rec"]["hp_cible_avant"], m["live"].get("hp_cible")
        if av is None or ap is None or int(ap) >= int(av):
            print("REFUS : la CIBLE n'a pris AUCUN degat live (%s -> %s) -- l'attaque n'a pas eu "
                  "lieu (hors portee ?), il n'y a rien a comparer" % (av, ap))
            return 2
        if m["splash_live"] is None or m["splash_port"] is None:
            print("REFUS : splash NON MESURE (live=%s port=%s)"
                  % (m["splash_live"], m["splash_port"]))
            return 2
        if bool(m["live"]["caster_mort"]) != bool(m["mort_attendue"]):
            print("REFUS : le bras n'a pas produit son regime (caster_mort=%s, attendu=%s)"
                  % (m["live"]["caster_mort"], m["mort_attendue"]))
            return 2
        if bool(m["offline"]["caster_mort"]) != bool(m["live"]["caster_mort"]):
            print("REFUS : la MORT du caster diverge (port=%s natif=%s) -- les deux cotes ne jouent "
                  "pas le meme coup" % (m["offline"]["caster_mort"], m["live"]["caster_mort"]))
            return 2
        if m["splash_live"] <= 0:
            print("REFUS : le NATIF n'applique AUCUN splash -- le montage ne discrimine rien")
            return 2
        if not m["mort_attendue"]:
            # BRAS TEMOIN : rien ne meurt, les deux cotes doivent etre BIT-EXACTS.
            if m["splash_port"] != m["splash_live"]:
                print("FAUTE : splash port=%s != natif=%s alors que PERSONNE ne meurt"
                      % (m["splash_port"], m["splash_live"]))
                rc |= 1
            return rc

        # --- BRAS REGIME : c'est ici que #951-r4 se tranche -------------------------------------
        o = m["ordre"]
        if o["splash"] is None or o["riposte"] is None:
            print("REFUS : ordre natif NON MESURE (splash=%s riposte=%s) -- sans le flux, on ne "
                  "peut pas dire si l'owner etait vivant" % (o["splash"], o["riposte"]))
            return 2
        if o["riposte"] < o["splash"]:
            print("FAUTE : le NATIF riposte AVANT le splash (#%s < #%s) -- alors le gate "
                  "`ownerNeedsToBeAlive` MORDRAIT, et il faut le porter" % (o["riposte"], o["splash"]))
            rc |= 1
        else:
            print("[%s] VERDICT : le natif draine la riposte APRES le splash -> l'owner est VIVANT "
                  "a `On(0x4a)`, le gate ne peut pas mordre." % m["bras"])
        # CLIQUET : le port doit appliquer un splash NON NUL. Poser le gate le mettrait a ZERO --
        # c'est exactement ce que la contre-epreuve `WITHGATE` demontre juste apres.
        if m["splash_port"] <= 0:
            print("FAUTE : le port n'applique AUCUN splash (%s) alors que le natif en applique %s "
                  "-- le gate `ownerNeedsToBeAlive` a-t-il ete pose ? (cf. #951-r4)"
                  % (m["splash_port"], m["splash_live"]))
            rc |= 1
        if m["splash_withgate"] != 0:
            print("FAUTE : la contre-epreuve WITHGATE ne ramene PAS le splash a zero (%s) -- elle "
                  "ne demontre alors rien" % m["splash_withgate"])
            rc |= 1
        else:
            print("[%s] mord   : True (port=%s vs WITHGATE=%s)"
                  % (m["bras"], m["splash_port"], m["splash_withgate"]))
        # DIVERGENCE DE RANG, NOMMEE et non assertee (residu `#951-r9`) : le port joue la riposte
        # AVANT ce vecteur, donc son caster a deja perdu un membre d'escouade quand le splash part.
        if m["splash_port"] != m["splash_live"]:
            print("[%s] ECART DE RANG (#951-r9) : splash port=%s natif=%s (%.0f %%) -- le port "
                  "joue la riposte AVANT `On(0x4a)`, le natif APRES."
                  % (m["bras"], m["splash_port"], m["splash_live"],
                     100.0 * m["splash_port"] / max(1, m["splash_live"])))
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--defender", default=DEFENDER,
                    help="le porteur de la RIPOSTE branchee sur `On(9)` -- par defaut "
                         "`darkaHellblaster` (`GrimRetribution`, `AttackDamage` DIRECT).")
    ap.add_argument("--voisin1", default="necroWarden")
    ap.add_argument("--voisin2", default="necroSpyder")
    ap.add_argument("--dist", type=int, default=2,
                    help="distance hex Vindicta <-> defenseur : >= 2, sinon la riposte "
                         "`GrimRetribution` est DESARMEE (elle exige zero ennemi adjacent).")
    ap.add_argument("--hp-target", type=int, default=900000,
                    help="PV des a-units : le defenseur ne doit PAS mourir du coup, sinon la "
                         "riposte ne part pas.")
    ap.add_argument("--hp-carrier", type=int, default=600,
                    help="`--hp-player` du bras REGIME -- assez bas pour que la riposte TUE "
                         "Vindicta (mesuree a ~2851 sur ce montage).")
    ap.add_argument("--hp-survivant", type=int, default=900000,
                    help="`--hp-player` du bras TEMOIN -- Vindicta encaisse la MEME riposte et "
                         "survit. Les deux bras ne different QUE par ce nombre.")
    ap.add_argument("--survivant", action="store_true",
                    help="BRAS TEMOIN : PV de Vindicta hors d'atteinte. Elle survit a la riposte, "
                         "donc le splash DOIT tomber, des deux cotes.")
    ap.add_argument("--essais", type=int, default=8,
                    help="nombre de plans de geometrie tentes avant d'abandonner (un `place` est "
                         "un vrai `MoveUnitOperation` et peut echouer).")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    print("== #951-r4 FireOfAbsolution / ownerNeedsToBeAlive -- board %s seed %s%s"
          % (a.board, a.seed, " [SURVIVANT]" if a.survivant else ""))

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    rc = run(a, rpc, Board, ChargeRegimeHarness)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
