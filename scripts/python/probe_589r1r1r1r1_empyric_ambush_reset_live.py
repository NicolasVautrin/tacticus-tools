#!/usr/bin/env python
"""probe #589-r1-r1-r1-r1 -- CONFRONTATION d'`EmpyricAmbush_Reset` (triggered 0x613 = 1555).

CRITERE BINAIRE, pose avant toute methode :

    « Quand `eldarLhykhis` ACHEVE un ennemi d'une attaque NORMALE au CONTACT, le natif re-arme-t-il
      son actif `EmpyricAmbush` (1232) -- et le PORT rend-il le MEME verdict, a partir du meme etat
      et du meme flux PRNG ? »

L'observable est l'ETAT D'UTILISATION de l'actif du TUEUR : `usable` / `cooldown` cote
`decisionView.units[].abilities` (natif), `ActiveAbilitiesComponent` cote port -- exactement les deux
champs que `IdunBattle.Operations.ResetActiveAbilityOperation$$Execute` ecrit
(`CanStillBeUsed = true`, cooldown remis a zero).

## LE MONTAGE, et pourquoi chaque piece y est

  * `eldarLhykhis` est HORS CATALOGUE du seed BC -> `catalog_inject.write_augmented_seed_bc`.
  * L'actif doit etre CONSOMME avant le kill, sinon le gate natif
    `IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset` rend FAUX et
    `ResetActiveAbility` est un no-op : rien ne discriminerait. On le consomme par un VRAI cast de
    1232 au tour 1, puis on tue au tour 2. Le probe VERIFIE que l'actif est encore non-utilisable
    juste avant le kill, et REFUSE (rc 2) sinon -- un regime non atteint n'est pas un accord.
  * Les ennemis sont TANKY (`--hp-target`) pour que le cast de 1232 (8 coups d'ability) ne tue
    PERSONNE : la mort doit venir de l'attaque NORMALE, sinon `IsNormalAttack` serait faux et le
    bras positif ne dirait rien. Le degat de Lhykhis est gonfle par `--unit-stat` pour que ses
    5 coups d'arme suffisent.
  * `--crit 0,0` / `--block-target 0,0` : aucun canal aleatoire ne vient decider de la mort.

## LES DEUX BRAS, et pourquoi il en faut DEUX

  * `MELEE` (defaut) -- le kill est porte au CONTACT. Le natif DOIT re-armer. La contre-epreuve
    `NOPORT` (l'entree `"EmpyricAmbush"` retiree d'`ACTIVE_ABILITY_TRIGGERS`, c.-a-d. la vue
    d'AVANT ce port) doit alors CHANGER l'observable : sans elle, « ca concorde » ne prouverait rien.
  * `--ranged` -- le MEME kill, la MEME attaque normale, a DISTANCE 2 (arme rangee de Lhykhis).
    Le natif ne DOIT PAS re-armer : c'est le noeud `IsMeleeAttack(<DSLSelectors+0x90>)` qui mord, et
    c'est le seul bras qui l'exerce. Sans lui le port pourrait rendre « re-arme sur tout kill » et
    concorder quand meme sur le bras positif.

Usage :
    python probe_589r1r1r1r1_empyric_ambush_reset_live.py
    python probe_589r1r1r1r1_empyric_ambush_reset_live.py --ranged
    python probe_589r1r1r1r1_empyric_ambush_reset_live.py --board C1_74 --seed 31337
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

CARRIER = "eldarLhykhis"          # porteur de l'actif 1232 -> triggered derivee 1555
ALLY = "blackHaarken"             # 2e unite de mon camp : elle n'agit pas
ABILITY_TYPE = 1232               # ActiveAbilityType 0x4d0 (l'actif re-arme)
RESET_TRIGGERED = 1555            # TriggeredAbilityType 0x613
REGISTRY_KEY = "EmpyricAmbush"    # cle d'`ACTIVE_ABILITY_TRIGGERS`


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _pos_of(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def seed_bc_avec_lhykhis() -> str:
    import catalog_inject
    fd, out = tempfile.mkstemp(prefix="probe_589r1r1r1r1_bc_", suffix=".json")
    os.close(fd)
    catalog_inject.write_augmented_seed_bc(out, [CARRIER])
    return out


def build(a, seed_bc):
    fd, sf = tempfile.mkstemp(prefix="probe_589r1r1r1r1_", suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--seed-bc", seed_bc,
            "--p-units", "%s,%s" % (CARRIER, ALLY),
            "--a-units", "%s,%s" % (a.target_unit, a.other_unit),
            "--hp-target", str(a.hp_target), "--hp-player", "900000",
            "--unit-stat", "%s:Damage=%d" % (CARRIER, a.dmg),
            "--no-ai", "--crit", "0,0", "--block-target", "0,0"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("build KO : %s" % ((p.stderr or p.stdout or "")[-700:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _active_state_live(dv, unit_id):
    """`usable` / `cooldown` de l'actif 1232 dans le `decisionView` -- l'oracle NATIF des deux
    champs qu'ecrit `ResetActiveAbilityOperation$$Execute`."""
    for u in (dv.get("units") or []):
        if u.get("id") == unit_id:
            for ab in (u.get("abilities") or []):
                if ab.get("id") == ABILITY_TYPE:
                    return {"usable": ab.get("usable"), "cooldown": ab.get("cooldown")}
    return None


def _active_state_port(st, unit_id):
    """Le pendant PORT : `ActiveAbilitiesComponent` (mirror d'`ActiveAbilityComponent`)."""
    from engine.runner.components import ActiveAbilitiesComponent
    e = st.get_entity(int(unit_id))
    comp = e.get_component(ActiveAbilitiesComponent) if e is not None else None
    if comp is None:
        return None
    for ab in comp.abilities:
        if int(ab.ability_type) == ABILITY_TYPE:
            return {"usable": bool(ab.can_still_be_used), "cooldown": ab.remaining_cooldown}
    return None


def stage(h, a):
    """Monte le regime et rend `(rec, raison)`. `raison is None` == regime ATTEINT.

    ETAPES : placements -> cycle de tour -> CAST de 1232 (consomme l'actif, ne tue personne)
    -> cycle de tour -> geometrie du kill (contact ou distance 2) -> snapshot -> (kill hors d'ici).
    """
    import hexgeo
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    if me is None:
        return None, "porteur %s absent du deploiement" % CARRIER
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) < 2:
        return None, "il faut 2 ennemis (un pour le cast, un temoin qui survit)"
    victime, temoin = ens[0], ens[1]

    marchables = [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]
    occupe = {p for p in (_pos_of(u) for u in h.alive(dv)) if p is not None}
    libres = [c for c in marchables if c not in occupe]

    def _n_voisins(c):
        return sum(1 for s in marchables if hexgeo.distance(s, c) == 1)

    # ANCRE de la victime : >= 5 voisins marchables et >= 3 contacts LIBRES (le `FlyUnit` de 1232
    # doit avoir de quoi atterrir), + des tuiles lointaines pour les autres.
    plan = None
    for anchor in sorted(libres, key=lambda c: (-_n_voisins(c), c)):
        if _n_voisins(anchor) < 5:
            break
        contacts = [s for s in libres if hexgeo.distance(s, anchor) == 1]
        loin = [s for s in libres if hexgeo.distance(s, anchor) >= 4]
        if len(contacts) >= 3 and len(loin) >= 3:
            plan = (anchor, loin)
            break
    if plan is None:
        return None, "geometrie non realisable (aucune ancre a >= 5 voisins / 3 contacts libres)"
    anchor, loin = plan

    if not h.place(victime["id"], anchor):
        return None, "placement de la victime refuse"
    if not h.place(me["id"], loin[0]):
        return None, "placement de Lhykhis refuse"
    h.place(temoin["id"], loin[1])
    ally = h.by_visual(ALLY)
    if ally is not None:
        h.place(ally["id"], loin[2])

    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint (avant le cast)"

    # --- CONSOMMATION de l'actif : un VRAI cast de 1232 sur la victime (qui SURVIT) -------------
    res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": me["id"], "targetId": victime["id"],
        "abilityType": ABILITY_TYPE}}, 60)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    if not a0.get("ok"):
        return None, "cast de 1232 refuse : %s" % str(res)[:300]
    dv = h.dview()
    vic = next((u for u in h.alive(dv) if u["id"] == victime["id"]), None)
    if vic is None:
        return None, "la victime est MORTE du cast -- augmenter --hp-target"
    apres_cast = _active_state_live(dv, me["id"])
    if apres_cast is None or apres_cast.get("usable"):
        return None, ("l'actif est encore utilisable APRES le cast (%s) -- rien a re-armer"
                      % apres_cast)

    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint (avant le kill)"

    # --- GEOMETRIE du kill : CONTACT (bras positif) ou DISTANCE 2 (bras `--ranged`) -------------
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    vic = next((u for u in h.alive(dv) if u["id"] == victime["id"]), None)
    if me is None or vic is None:
        return None, "une unite a disparu apres le cycle de tour"
    vpos = _pos_of(vic)
    want = 2 if a.ranged else 1
    occupe = {p for p in (_pos_of(u) for u in h.alive(dv)) if p is not None} - {_pos_of(me)}
    if hexgeo.distance(_pos_of(me), vpos) != want:
        dest = next((c for c in marchables
                     if hexgeo.distance(c, vpos) == want and c not in occupe), None)
        if dest is None:
            return None, "aucune tuile a distance %d de la victime" % want
        if not h.place(me["id"], dest):
            return None, "placement de Lhykhis a distance %d refuse" % want
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    dist = hexgeo.distance(_pos_of(me), vpos)
    if dist != want:
        return None, "distance obtenue %d != %d" % (dist, want)

    # REGIME : l'actif doit encore etre NON utilisable a cet instant precis.
    avant = _active_state_live(dv, me["id"])
    if avant is None:
        return None, "actif 1232 absent du decisionView"
    if avant.get("usable"):
        return None, ("l'actif s'est re-arme TOUT SEUL avant le kill (%s) -- le cooldown a expire, "
                      "le regime ne discrimine plus rien" % avant)

    nat = h.normal_attack_type(me["id"], dv)
    if nat is None:
        return None, "attaque normale introuvable pour Lhykhis"
    rec = {"caster": me["id"], "target": victime["id"], "step_to": None,
           "ability_type": nat, "dist": dist, "avant": avant,
           "caster_pos": _pos_of(me), "target_pos": vpos}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    if a.verbose:
        print("    Lhykhis en %s, victime en %s (dist %d), actif avant = %s, attaque normale %s"
              % (rec["caster_pos"], vpos, dist, avant, nat))
    return rec, None


def kill_live(h, rec):
    """L'ATTAQUE NORMALE native. Rend `(observables, raison)`."""
    res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": int(rec["ability_type"])}}, 60)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    if not a0.get("ok"):
        return None, "attaque normale refusee : %s" % str(res)[:300]
    dv = h.dview()
    vic = next((u for u in (dv.get("units") or []) if u.get("id") == rec["target"]), None)
    mort = vic is None or vic.get("dead") is True or (vic.get("hp") in (0, None) and
                                                     not vic.get("alive", True))
    ob = h.rpc("observeBattle", {"runnerId": h.rid}, 40) or {}
    for u in (ob.get("units") or []):
        if u.get("id") == rec["target"]:
            mort = bool(u.get("isDead"))
    return {"mort": bool(mort), "apres": _active_state_live(dv, rec["caster"])}, None


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE de la MEME attaque normale, RNG cale sur le dump pris juste avant.

    MUTATION `NOPORT` : l'entree `"EmpyricAmbush"` retiree d'`ACTIVE_ABILITY_TRIGGERS` -- c'est le
    registre qui materialise la triggered derivee, donc son retrait rend la vue d'AVANT ce port
    (aucun `EmpyricAmbush_Reset` instancie, donc aucun re-armement). Restauree en `finally`."""
    from engine.runner.components import UnitComponent
    from engine.runner.operations.triggers.dispatch.registry import ACTIVE_ABILITY_TRIGGERS
    saved = ACTIVE_ABILITY_TRIGGERS.get(REGISTRY_KEY)
    try:
        if mutate == "NOPORT":
            ACTIVE_ABILITY_TRIGGERS.pop(REGISTRY_KEY, None)
        res = h.replay_offline(rec)
        st = res["state"]
        e = st.get_entity(rec["target"])
        uc = e.get_component(UnitComponent) if e is not None else None
        return {"mort": bool(uc is not None and not uc.alive),
                "apres": _active_state_port(st, rec["caster"]),
                "per_hit": res.get("per_hit") or []}
    finally:
        if saved is not None:
            ACTIVE_ABILITY_TRIGGERS[REGISTRY_KEY] = saved


def stage_par_ability(h, a):
    """BRAS `--par-ability` : la victime est FRAGILE et meurt des 8 coups du cast de 1232 lui-meme.
    Le `killTrigger` du vecteur mort est alors l'ability 1232, donc `IsNormalAttack(<+0x90>)` est
    FAUX et le natif ne DOIT PAS re-armer. C'est le seul bras qui exerce ce noeud-la : les deux
    autres tuent par une attaque NORMALE, ou il est vrai par construction.

    Le snapshot est pris AVANT le cast -- c'est lui que le rejeu offline consomme."""
    import hexgeo
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    if me is None:
        return None, "porteur %s absent du deploiement" % CARRIER
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) < 2:
        return None, "il faut 2 ennemis (la victime + un temoin qui garde la bataille en vie)"
    victime, temoin = ens[0], ens[1]

    marchables = [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]
    occupe = {p for p in (_pos_of(u) for u in h.alive(dv)) if p is not None}
    libres = [c for c in marchables if c not in occupe]

    def _n_voisins(c):
        return sum(1 for s in marchables if hexgeo.distance(s, c) == 1)

    plan = None
    for anchor in sorted(libres, key=lambda c: (-_n_voisins(c), c)):
        if _n_voisins(anchor) < 5:
            break
        contacts = [s for s in libres if hexgeo.distance(s, anchor) == 1]
        loin = [s for s in libres if hexgeo.distance(s, anchor) >= 4]
        if len(contacts) >= 3 and len(loin) >= 3:
            plan = (anchor, loin)
            break
    if plan is None:
        return None, "geometrie non realisable"
    anchor, loin = plan
    if not h.place(victime["id"], anchor):
        return None, "placement de la victime refuse"
    if not h.place(me["id"], loin[0]):
        return None, "placement de Lhykhis refuse"
    h.place(temoin["id"], loin[1])
    ally = h.by_visual(ALLY)
    if ally is not None:
        h.place(ally["id"], loin[2])
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    if me is None:
        return None, "Lhykhis a disparu apres le cycle de tour"
    avant = _active_state_live(dv, me["id"])
    if avant is None or not avant.get("usable"):
        return None, "l'actif n'est PAS utilisable avant le cast (%s)" % avant
    rec = {"caster": me["id"], "target": victime["id"], "step_to": None, "avant": avant}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    return rec, None


def cast_kill_live(h, rec):
    """Le CAST de 1232, qui TUE la victime. Rend `(observables, raison)`."""
    res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": ABILITY_TYPE}}, 60)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    if not a0.get("ok"):
        return None, "cast refuse : %s" % str(res)[:300]
    ob = h.rpc("observeBattle", {"runnerId": h.rid}, 40) or {}
    rows = [u for u in (ob.get("units") or []) if u.get("id") == rec["target"]]
    mort = (not rows) or bool(rows[0].get("isDead"))   # absente d'`observeBattle` == retiree = morte
    return {"mort": bool(mort), "apres": _active_state_live(h.dview(), rec["caster"])}, None


def replay_cast(h, rec):
    """Rejeu OFFLINE du MEME cast (`ActiveAbilityMessage` 1232), RNG cale sur le dump pris avant.
    Rend aussi l'etat post-cast, sur lequel on interroge DIRECTEMENT le noeud `IsNormalAttack`."""
    from engine.runner.components import UnitComponent
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = h.offline_state(rec)
    Runner(st).install_default_handlers(20).apply(
        ActiveAbilityMessage(caster_id=rec["caster"], target_id=rec["target"],
                             ability_type=ABILITY_TYPE))
    e = st.get_entity(rec["target"])
    uc = e.get_component(UnitComponent) if e is not None else None
    return {"mort": bool(uc is not None and not uc.alive),
            "apres": _active_state_port(st, rec["caster"]), "state": st}


def run_par_ability(h, a) -> int:
    rec, why = stage_par_ability(h, a)
    if rec is None:
        print("REFUS (montage) : %s" % why)
        return 2
    live, why = cast_kill_live(h, rec)
    if live is None:
        print("REFUS (cast live) : %s" % why)
        return 2
    off = replay_cast(h, rec)
    print("[PAR-ABILITY] avant   : %s" % rec["avant"])
    print("[PAR-ABILITY] LIVE    : mort=%s actif=%s" % (live["mort"], live["apres"]))
    print("[PAR-ABILITY] OFFLINE : mort=%s actif=%s" % (off["mort"], off["apres"]))
    if not live["mort"]:
        print("REFUS : la victime n'est pas morte du CAST -- baisser --hp-target")
        return 2
    if not off["mort"]:
        print("REFUS : la victime n'est pas morte OFFLINE -- les deux cotes ne jouent pas le meme coup")
        return 2
    nat = (live["apres"] or {}).get("usable")
    if nat is None:
        print("REFUS : etat d'actif natif NON MESURE")
        return 2
    if nat is not False:
        print("REFUS : le NATIF a re-arme sur un kill d'ABILITY (usable=%s) -- ce bras suppose le "
              "contraire, la RE est a reprendre" % nat)
        return 2

    # L'observable `usable` cote PORT est SATUREE sur ce bras : le port ne modelise pas la
    # consommation de l'actif au cast offline (l'`ActiveAbilitiesComponent` est SEEDE depuis le
    # `decisionView` d'AVANT, donc `usable=True`), et un gate `EntityCanHaveActiveAbilityReset` faux
    # rend le re-armement no-op quoi qu'il arrive. On interroge donc le NOEUD directement, sur le
    # MEME etat post-cast : c'est la seule facon de le confronter ici, et c'est dit plutot que
    # maquille en accord.
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.abilities.attack_type import is_normal_attack
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.loki.empyric_ambush import (
        EmpyricAmbushResetAbility, _kill_trigger)
    st = off["state"]
    kt = _kill_trigger(st, rec["target"])
    ev = TriggerEvent(int(EventTriggerType.UnitDefeated), rec["caster"], rec["target"],
                      ranged=False, profile=None,
                      killer_id=rec["caster"], dying_id=rec["target"])
    fired = EmpyricAmbushResetAbility(rec["caster"]).matches(st, ev)
    print("[PAR-ABILITY] port    : killTrigger=%s is_normal_attack=%s matches=%s"
          % (kt, is_normal_attack(kt), fired))
    if kt is None:
        print("REFUS : le canal `death_source` est VIDE -- le noeud n'est pas exerce")
        return 2
    if is_normal_attack(kt):
        print("REFUS : le killTrigger %s est vu comme une attaque NORMALE -- regime non atteint" % kt)
        return 2
    if fired:
        print("FAUTE : le port declenche EmpyricAmbush_Reset sur un kill d'ABILITY "
              "(`IsNormalAttack` ne mord pas)")
        return 1
    print("[PAR-ABILITY] NOTE : l'observable `usable` cote port est SATUREE (le port ne consomme pas "
          "l'actif au cast offline) -- le noeud est confronte au niveau du PREDICAT, pas de l'etat.")
    return 0


def run(a, rpc, Board, Harness, seed_bc) -> int:
    rid, sf = build(a, seed_bc)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        if a.par_ability:
            return run_par_ability(h, a)
        rec, why = stage(h, a)
        if rec is None:
            print("REFUS (montage) : %s" % why)
            return 2

        live, why = kill_live(h, rec)
        if live is None:
            print("REFUS (kill live) : %s" % why)
            return 2
        off = replay(h, rec)
        mut = replay(h, rec, mutate="NOPORT")

        bras = "RANGED (dist 2)" if a.ranged else "MELEE (contact)"
        attendu = not a.ranged                    # re-armement attendu SEULEMENT au contact
        print("[%s] avant   : %s" % (bras, rec["avant"]))
        print("[%s] LIVE    : mort=%s actif=%s" % (bras, live["mort"], live["apres"]))
        print("[%s] OFFLINE : mort=%s actif=%s (per_hit=%s)"
              % (bras, off["mort"], off["apres"], off["per_hit"][:4]))
        print("[%s] NOPORT  : actif=%s" % (bras, mut["apres"]))

        rc = 0
        if not live["mort"]:
            print("REFUS : la victime n'est PAS morte du coup -- augmenter --dmg / baisser --hp-target")
            return 2
        if not off["mort"]:
            print("REFUS : la victime n'est pas morte OFFLINE -- les deux cotes ne jouent pas le "
                  "meme coup, l'accord sur l'actif ne prouverait rien")
            return 2
        nat_usable = (live["apres"] or {}).get("usable")
        port_usable = (off["apres"] or {}).get("usable")
        if nat_usable is None or port_usable is None:
            print("REFUS : etat d'actif NON MESURE (natif=%s port=%s)" % (nat_usable, port_usable))
            return 2
        if bool(nat_usable) != bool(attendu):
            print("REFUS : le NATIF ne fait pas ce que le bras attend (usable=%s, attendu=%s) -- "
                  "le regime ne discrimine pas" % (nat_usable, attendu))
            return 2
        if bool(port_usable) != bool(nat_usable):
            print("FAUTE : port usable=%s != natif usable=%s" % (port_usable, nat_usable))
            rc |= 1
        # La contre-epreuve doit MORDRE, et seulement la ou elle le peut : sur le bras RANGED le
        # natif ne re-arme pas, donc `NOPORT` ne PEUT rien changer -- on ne l'exige pas.
        if not a.ranged:
            mord = (mut["apres"] or {}).get("usable") is False
            print("[%s] mord   : %s" % (bras, mord))
            if not mord:
                print("FAUTE : NOPORT n'a rien change -- l'accord ne prouve rien")
                rc |= 1
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--target-unit", default="necroWarden")
    ap.add_argument("--other-unit", default="necroOverlord")
    ap.add_argument("--hp-target", type=int, default=900000)
    ap.add_argument("--dmg", type=int, default=400000,
                    help="stat Damage de Lhykhis (--unit-stat) : ses 5 coups d'arme doivent TUER "
                         "un ennemi a --hp-target PV, la ou les 8 coups de 1232 ne le peuvent pas.")
    ap.add_argument("--ranged", action="store_true",
                    help="BRAS NEGATIF : le kill est porte a DISTANCE 2 -- `IsMeleeAttack` doit "
                         "REFUSER le re-armement, des deux cotes.")
    ap.add_argument("--par-ability", action="store_true", dest="par_ability",
                    help="BRAS NEGATIF : la victime meurt du CAST de 1232 (pas d'une attaque "
                         "normale) -- `IsNormalAttack` doit REFUSER le re-armement. Prendre un "
                         "`--hp-target` assez BAS pour que les 8 coups d'ability tuent.")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.par_ability and a.hp_target > 20000:
        a.hp_target = 2000            # defaut PROPRE a ce bras : la victime doit mourir du cast

    print("== #589-r1-r1-r1-r1 EmpyricAmbush_Reset (triggered %d) -- board %s seed %s%s"
          % (RESET_TRIGGERED, a.board, a.seed,
             " [RANGED]" if a.ranged else (" [PAR-ABILITY]" if a.par_ability else "")))

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
