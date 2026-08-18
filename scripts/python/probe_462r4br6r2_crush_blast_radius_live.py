#!/usr/bin/env python
"""probe #462-r4b-r1-r1-r1-r1-c-r3-r1-r6-r2 -- les DEUX classes du blast radius du CRUSH, CONFRONTEES.

CRITERE BINAIRE, pose avant toute methode :

    << Quand une unite ECRASE un `Steppable` en se deplacant dessus, le natif fait-il fire
       `HazeCorruption_BonusHitAbility` (le coup Toxic bonus) et `DawnBlade_HealAbility` (la
       reparation du tueur) -- et le PORT rend-il le MEME verdict pour chacune ? >>

Les deux gates ont ete LUS par `#462-...-r6` (owner = le TUEUR, donc atteignables par le MOVER),
mais aucune des deux n'avait jamais ete opposee au jeu : c'est le residu `-r6-r2`, un verdict
ANALYTIQUE. Sa << condition de retournement executable >> est reprise telle quelle : porter chacune
sur une unite reelle, ecraser un `Steppable` avec elle, et comparer natif/port AVEC TEMOIN (meme
montage, aucun crush).

## LE MONTAGE, et pourquoi chaque piece y est

  * Le `Steppable` est une MINE HAYWIRE : `astarCyrus` (injecte au catalogue) en pose une sur sa
    tuile PRECEDENTE a chaque pas (`On(0x29 = UnitFinishedTurnNormally)`, cf.
    `probe_462_..._r5_haywire_pose.py`). C'est le seul `Steppable` qu'on sache faire apparaitre a
    volonte sans piloter l'IA adverse.
  * La mine est de MON camp, comme le mover : `HaywireMineSteppableAbility` est gatee `AreEnemies`,
    donc elle n'attaque PAS le mover et ne pollue AUCUN observable de degat. Une mine ennemie
    aurait melange sa propre attaque au coup Toxic qu'on cherche.
  * Le MOVER porte REELLEMENT l'ability confrontee : `deathBlightlord` (<< Maladus >>) pour
    `HazeOfCorruption`, `tauFarsight` + `--equip-relic tauFarsight:DawnBlade` pour la relique. Rien
    n'est greffe a la main.
  * Bras `DawnBlade` seulement : le mover doit etre ENDOMMAGE avant le crush, sinon le gate
    `EntityCanBeRepaired` / `IsDamagedUnit` refuse la reparation et l'observable est nul des deux
    cotes -- un accord qui ne prouverait rien. On le fait frapper par un ennemi (les DEUX camps
    sont pilotables par `applyAction`).

## LES DEUX OBSERVABLES, et le tiers qui les explique

  * `HazeCorruption_BonusHitAbility` -> un evenement de degat `DamageProfileType 24` (Toxic) du
    MOVER sur le crushe, dans le flux du `move`.
  * `DawnBlade_HealAbility` -> les PV du MOVER remontent au crush.
  * et `decisionView.units[<crushe>].defeatedByMelee` (publie depuis #185) : c'est LUI qui dit si le
    conjoint `IsDefeatedByMeleeAttack` du trigger `DawnBlade` peut etre vrai. Le port, lui,
    l'APPROXIME positionnellement (`_is_ranged_position`), et apres un crush le mover est SUR la
    tuile du crushe -- distance 0, donc << melee >> pour l'approximation. Si le natif dit `false`,
    les deux ne peuvent pas etre d'accord.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_462r4br6r2_crush_blast_radius_live.py --face haze
    python probe_462r4br6r2_crush_blast_radius_live.py --face dawnblade
    python probe_462r4br6r2_crush_blast_radius_live.py --face haze --temoin-sans-crush
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

POSEUR = "astarCyrus"              # pose une mine HAYWIRE (`Steppable`) a chaque pas
MINE = "HaywireMine"               # fragment de `visualId` du summon
FACES = {
    # face -> (visualId du mover, ability confrontee, args `rl_duel build` supplementaires)
    "haze": ("deathBlightlord", "HazeOfCorruption", []),
    "dawnblade": ("tauFarsight", "DawnBlade", ["--equip-relic", "tauFarsight:DawnBlade"]),
}
TOXIC_PROFILE = 24                 # `DamageProfileType` du coup bonus de `HazeOfCorruption`


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _pos_of(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def seed_bc_avec_poseur() -> str:
    import catalog_inject
    fd, out = tempfile.mkstemp(prefix="probe_462r6r2_bc_", suffix=".json")
    os.close(fd)
    catalog_inject.write_augmented_seed_bc(out, [POSEUR])
    return out


def build(a, seed_bc):
    mover, _ability, extra = FACES[a.face]
    fd, sf = tempfile.mkstemp(prefix="probe_462r6r2_", suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--seed-bc", seed_bc, "--rank", "17",
            "--p-units", "%s,%s" % (POSEUR, mover),
            "--a-units", "%s,%s" % (a.ennemi1, a.ennemi2),
            "--hp-target", str(a.hp_target), "--hp-player", str(a.hp_player),
            "--no-ai", "--crit", "0,0", "--crit-target", "0,0",
            "--block-target", "0,0", "--block-player", "0,0", *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("build KO : %s" % ((p.stderr or p.stdout or "")[-900:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _mines(dv):
    return [u for u in (dv.get("units") or [])
            if u.get("alive") and MINE in (u.get("visualId") or "")]


def _unit(dv, unit_id):
    for u in (dv.get("units") or []):
        if u.get("id") == unit_id:
            return u
    return None


def _coups(events):
    """Les evenements de DEGAT du flux natif, dans l'ORDRE, tags decodes."""
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


def _atteindre_tour_adverse(h, maxi=8):
    """Enchaine des `endturn` jusqu'a ce que le joueur courant ne soit PLUS le mien.

    Pendant du `reach_my_turn` du harnais, dans l'autre sens : il faut le tour de l'ADVERSAIRE pour
    qu'une de ses unites puisse REELLEMENT agir (le natif refuse en silence l'action d'une unite
    hors de son tour)."""
    for _ in range(maxi):
        dv = h.dview()
        if dv.get("currentPlayer") != h.my_player:
            return dv
        h.rpc("applyAction", {"runnerId": h.rid, "action": {"kind": "endturn"}}, 40)
        h.endturns += 1
    return None


def stage(h, a):
    """Monte le regime et rend `(rec, raison)`. `raison is None` == regime ATTEINT.

    ETAPES : placements -> (bras `dawnblade`) un ennemi FRAPPE le mover pour l'endommager ->
    `astarCyrus` fait UN PAS, ce qui POSE une mine sur sa tuile precedente -> on ramene le mover a
    portee de cette mine -> SNAPSHOT -> le crush est porte hors d'ici."""
    import hexgeo
    mover_vis, ability, _extra = FACES[a.face]
    dv = h.dview()
    poseur = h.by_visual(POSEUR, dv)
    mover = h.by_visual(mover_vis, dv)
    if poseur is None or mover is None:
        return None, "poseur=%s / mover=%s absent du deploiement" % (POSEUR, mover_vis)
    h.my_player = mover.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if not ens:
        return None, "aucun ennemi (il en faut un pour endommager le mover)"

    marchables = [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]

    def _libres(extra_exclue=()):
        occ = {p for p in (_pos_of(u) for u in h.alive()) if p is not None}
        return [c for c in marchables if c not in occ and c not in set(extra_exclue)]

    # --- (1) le mover est ENDOMMAGE (bras `dawnblade` seulement) ------------------------------
    # `DawnBlade_HealAbility` passe par `RepairUnitOperation`, donc par `EntityCanBeRepaired` : un
    # porteur a PV PLEINS ne recupere RIEN. Sans cette etape, le bras rendrait 0 des deux cotes --
    # un accord qui ne prouve rien (le regime DEGENERE que la doctrine refuse).
    if a.face == "dawnblade":
        frappeur = ens[0]
        libres = _libres()
        contact = next((c for c in libres
                        if hexgeo.distance(c, _pos_of(mover)) == 1), None)
        if contact is None or not h.place(frappeur["id"], contact):
            return None, "impossible d'amener un frappeur au contact du mover"
        # ⚠ LE FRAPPEUR DOIT AGIR PENDANT SON PROPRE TOUR. `applyAction` pilote les deux camps, mais
        # le natif REFUSE EN SILENCE (`ok=True`, aucun degat) l'action d'une unite dont ce n'est pas
        # le tour -- mesure : `hp 900000 -> 900000`. On rend donc la main a l'adversaire.
        if _atteindre_tour_adverse(h) is None:
            return None, "tour adverse non atteint (avant la frappe)"
        nat = h.normal_attack_type(frappeur["id"], h.dview())
        if nat is None:
            return None, "attaque normale introuvable pour le frappeur"
        # ⚠ `decisionView` ne publie PAS `hpMax` : on compare les PV AVANT/APRES la frappe plutot
        # que de tester `hp < hpMax`, qui rendait `None` et faisait refuser un montage SAIN.
        hp_avant_frappe = (_unit(h.dview(), mover["id"]) or {}).get("hp")
        h.rpc("applyAction", {"runnerId": h.rid, "action": {
            "kind": "ability", "casterId": frappeur["id"], "targetId": mover["id"],
            "abilityType": int(nat)}}, 60)
        dv = h.dview()
        um = _unit(dv, mover["id"])
        if (um is None or hp_avant_frappe is None or um.get("hp") is None
                or int(um["hp"]) >= int(hp_avant_frappe)):
            return None, ("le mover n'est PAS endommage (hp %s -> %s) -- le gate "
                          "`EntityCanBeRepaired` refuserait la reparation"
                          % (hp_avant_frappe, (um or {}).get("hp")))
        # le frappeur repart au loin : il ne doit ni bloquer la geometrie ni encaisser quoi que ce
        # soit du crush.
        loin = [c for c in _libres() if hexgeo.distance(c, _pos_of(mover)) >= 5]
        if loin:
            h.place(frappeur["id"], loin[0])

    # --- (1bis) BRAS DE NON-DEGENERESCENCE : le mover TUE par une ATTAQUE, pas par un crush -----
    # Sans lui, << le natif ne fire pas au crush >> ne distingue pas << le crush ne l'arme pas >> de
    # << l'ability n'est pas montee sur ce porteur >>. Ici on ne pose AUCUNE mine : le regime est
    # la mort ORDINAIRE d'un ennemi adjacent.
    if a.temoin_kill_attaque:
        victime = ens[-1]
        libres = _libres()
        contact = next((c for c in libres if hexgeo.distance(c, _pos_of(mover)) == 1), None)
        if contact is None or not h.place(victime["id"], contact):
            return None, "impossible d'amener une victime au contact du mover"
        if h.reach_my_turn(force_cycle=True) is None:
            return None, "mon tour non atteint (avant le kill temoin)"
        dv = h.dview()
        mover = h.by_visual(mover_vis, dv)
        nat = h.normal_attack_type(mover["id"], dv)
        if nat is None:
            return None, "attaque normale introuvable pour le mover"
        rec = {"mover": mover["id"], "mine": victime["id"], "step_to": None,
               "caster": mover["id"], "ability": ability, "mine_pos": _pos_of(victime),
               "ability_type": int(nat),
               "hp_avant": (_unit(dv, mover["id"]) or {}).get("hp"),
               "hpmax": (_unit(dv, mover["id"]) or {}).get("hpMax"),
               "pos_avant": _pos_of(mover)}
        rec["snapshot"] = h.snapshot()
        rec["rng_after_step"] = rec["snapshot"]["rng"]
        return rec, None

    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint (avant la pose de mine)"

    # --- (2) POSE de la mine : `astarCyrus` fait UN PAS ---------------------------------------
    dv = h.dview()
    poseur = h.by_visual(POSEUR, dv)
    depart = _pos_of(poseur)
    voisines = [c for c in _libres() if hexgeo.distance(c, depart) == 1]
    if not voisines:
        return None, "aucune tuile libre adjacente au poseur"
    if not h.place(poseur["id"], voisines[0]):
        return None, "le pas du poseur a echoue -- aucune mine ne sera posee"
    # La pose tombe a la CLOTURE du tour de l'unite : on la force.
    h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "finish", "unitId": poseur["id"]}}, 40)
    dv = h.dview()
    mines = _mines(dv)
    if not mines:
        return None, "aucune mine posee apres le pas du poseur (events ?)"
    mine = mines[0]
    mine_pos = _pos_of(mine)

    # --- (3) le mover doit pouvoir ATTEINDRE la mine -------------------------------------------
    dv = h.dview()
    mover = h.by_visual(mover_vis, dv)
    if mover is None:
        return None, "le mover a disparu"
    if hexgeo.distance(_pos_of(mover), mine_pos) > 1:
        adj = [c for c in _libres((mine_pos,)) if hexgeo.distance(c, mine_pos) == 1]
        if not adj or not h.place(mover["id"], adj[0]):
            return None, "impossible d'amener le mover au contact de la mine"
        dv = h.dview()
        mover = h.by_visual(mover_vis, dv)

    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint (avant le crush)"
    dv = h.dview()
    mover = h.by_visual(mover_vis, dv)
    mine = next((u for u in _mines(dv) if u["id"] == mine["id"]), None)
    if mover is None or mine is None:
        return None, "mover ou mine disparus apres le cycle de tour"

    # TEMOIN : on vise une tuile LIBRE adjacente, pas la mine -> aucun crush, tout le reste egal.
    cible = mine_pos
    if a.temoin_sans_crush:
        libres_adj = [c for c in _libres((mine_pos,))
                      if hexgeo.distance(c, _pos_of(mover)) == 1]
        if not libres_adj:
            return None, "aucune tuile libre adjacente pour le bras TEMOIN"
        cible = libres_adj[0]

    rec = {"mover": mover["id"], "mine": mine["id"], "step_to": cible, "caster": mover["id"],
           "ability": ability, "mine_pos": mine_pos,
           "hp_avant": (_unit(dv, mover["id"]) or {}).get("hp"),
           "hpmax": (_unit(dv, mover["id"]) or {}).get("hpMax"),
           "pos_avant": _pos_of(mover)}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = rec["snapshot"]["rng"]
    return rec, None


def crush_live(h, rec, a):
    """Le PAS natif -- c'est lui qui ecrase la mine. Rend `(observables, raison)`.

    Sur le bras `--temoin-kill-attaque` il n'y a PAS de pas : c'est une attaque normale."""
    if a.temoin_kill_attaque:
        res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
            "kind": "ability", "casterId": rec["mover"], "targetId": rec["mine"],
            "abilityType": int(rec["ability_type"])}}, 60)
    else:
        res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
            "kind": "move", "unitId": rec["mover"],
            "to": {"col": int(rec["step_to"][0]), "row": int(rec["step_to"][1])}}}, 60)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    dv = h.dview()
    um = _unit(dv, rec["mover"])
    mine = _unit(dv, rec["mine"])
    coups = _coups(a0.get("events") or (res.get("events") if isinstance(res, dict) else None))
    toxic = [t for t in coups
             if t.get("Attacker_Id") == rec["mover"] and int(t.get("DamageProfileType") or -1)
             == TOXIC_PROFILE]
    bruts = a0.get("events") or (res.get("events") if isinstance(res, dict) else None) or []
    # ⚠ L'OBSERVABLE EST LE **GROUPE**, PAS LE COUP. Mesure : sur un kill ordinaire, le natif ouvre
    # bien un `group{source: "HazeOfCorruption"}` APRES la mort -- mais il n'y publie AUCUN
    # evenement de degat, parce que la victime est deja retiree (`Unit_IsDying`,
    # `NumberOfMembers: 0`) et que le coup bonus vaut `Amount 0` sur un cadavre. Compter les coups
    # rendrait donc << le natif ne fire pas >> pour une ability qui fire.
    groupes = [e for e in bruts
               if e.get("kind") == "group" and (e.get("source") or "") == rec["ability"]]
    return ({"hp_apres": (um or {}).get("hp"), "pos_apres": _pos_of(um),
             "mine_vivante": bool((mine or {}).get("alive")),
             "defeated_by_melee": (mine or {}).get("defeatedByMelee"),
             "killer_id": (mine or {}).get("killerId"),
             "coups": coups, "toxic": toxic, "groupes": groupes,
             "n_events": len(bruts), "bruts": bruts}, None)


def replay(h, rec):
    """Rejeu OFFLINE du MEME pas, RNG cale sur le dump pris juste avant.

    On ESPIONNE les deux classes plutot que de deviner leur verdict d'apres les PV : un port qui ne
    fire pas rend le meme observable qu'un port absent."""
    from engine.runner.components import HealthComponent, UnitComponent
    from engine.runner.operations.triggers.loki import dawn_blade as DB
    from engine.runner.operations.triggers.loki import haze_of_corruption as HZ

    traces = {"haze": [], "dawnblade": []}
    orig_h, orig_d = HZ.HazeCorruptionBonusHitAbility.matches, DB.DawnBladeHealAbility.matches

    def _espion(cle, orig):
        def _f(self, state, ev):
            v = bool(orig(self, state, ev))
            traces[cle].append({"event": int(ev.event_id), "owner": int(self.owner_id),
                                "killer": ev.killer_id, "dying": ev.dying_id, "verdict": v})
            return v
        return _f

    HZ.HazeCorruptionBonusHitAbility.matches = _espion("haze", orig_h)
    DB.DawnBladeHealAbility.matches = _espion("dawnblade", orig_d)
    try:
        st = h.offline_state(rec)          # rejoue `MoveUnitMessage(mover, step_to)`
        e = st.get_entity(rec["mover"])
        hc = e.get_component(HealthComponent) if e is not None else None
        m = st.get_entity(rec["mine"])
        muc = m.get_component(UnitComponent) if m is not None else None
        return {"hp_apres": None if hc is None else int(hc.hp),
                "mine_vivante": bool(muc is not None and muc.alive),
                "traces": traces,
                "fire": {k: any(t["verdict"] for t in v) for k, v in traces.items()}}
    finally:
        HZ.HazeCorruptionBonusHitAbility.matches = orig_h
        DB.DawnBladeHealAbility.matches = orig_d


def mesurer(a, rpc, Board, Harness, rid) -> dict:
    """LA MESURE, sur un runner DEJA construit -- sans impression ni verdict."""
    # ⚠ TRANSPORT AMBIANT OBLIGATOIRE sur la face `dawnblade` : la relique est une GREFFE declaree,
    # et `load_state` REFUSE de charger un etat greffe si le canal `unitAbilityStates` est muet
    # (#448-r3-r1-r1) -- sans lui, la classe `DawnBladeHealAbility` ne serait pas montee offline et
    # l'assertion negative passerait a VIDE, en vert.
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(rpc)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
    bras = "%s%s%s" % (a.face.upper(), " / TEMOIN SANS CRUSH" if a.temoin_sans_crush else "",
                       " / TEMOIN KILL PAR ATTAQUE" if a.temoin_kill_attaque else "")
    rec, why = stage(h, a)
    if rec is None:
        return {"ok": False, "why": "montage : %s" % why, "bras": bras}
    live, why = crush_live(h, rec, a)
    if live is None:
        return {"ok": False, "why": "crush live : %s" % why, "bras": bras}
    off = replay(h, rec)
    return {"ok": True, "why": None, "bras": bras, "face": a.face,
            "crush_attendu": (not a.temoin_sans_crush),
            "temoin_kill_attaque": bool(a.temoin_kill_attaque),
            "rec": {k: rec[k] for k in ("mover", "mine", "step_to", "mine_pos", "hp_avant",
                                        "hpmax", "pos_avant", "ability")},
            "live": live, "offline": off, "_h": h, "_rec": rec}


def run(a, rpc, Board, Harness, seed_bc) -> int:
    rid, sf = build(a, seed_bc)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        m = mesurer(a, rpc, Board, Harness, rid)
        if not m.get("ok"):
            print("REFUS (%s)" % m.get("why"))
            return 2
        rec, live, off = m["rec"], m["live"], m["offline"]
        print("[%s] mover=%s hp %s/%s en %s -> pas vers %s (mine %s en %s)"
              % (m["bras"], rec["mover"], rec["hp_avant"], rec["hpmax"], rec["pos_avant"],
                 rec["step_to"], rec["mine"], rec["mine_pos"]))
        print("[%s] LIVE    : mine_vivante=%s defeatedByMelee=%s killerId=%s hp=%s coups=%d "
              "toxic=%d" % (m["bras"], live["mine_vivante"], live["defeated_by_melee"],
                            live["killer_id"], live["hp_apres"], len(live["coups"]),
                            len(live["toxic"])))
        print("[%s] OFFLINE : mine_vivante=%s hp=%s fire=%s"
              % (m["bras"], off["mine_vivante"], off["hp_apres"], off["fire"]))
        for cle, tr in (off.get("traces") or {}).items():
            for t in tr:
                print("    [espion %s] %s" % (cle, t))
        if a.verbose:
            print("    [events natifs] %d au total" % live.get("n_events", 0))
            for i, t in enumerate(live["coups"]):
                print("    [coup %02d] att=%s -> tgt=%s amount=%s profil=%s passif=%s ability=%s"
                      % (i, t.get("Attacker_Id"), t.get("Target_Id"), t.get("Amount"),
                         t.get("DamageProfileType"), t.get("Passive_Ability_Type"),
                         t.get("Active_Ability_Type")))
            for e in (live.get("bruts") or []):
                print("    [ev] %s" % (json.dumps(e)[:300]))

        rc = 0
        mort_live = (not live["mine_vivante"])
        if mort_live is not bool(m["crush_attendu"]):
            print("REFUS : le bras n'a pas produit son regime (victime morte=%s, attendu=%s)"
                  % (mort_live, m["crush_attendu"]))
            return 2
        if a.temoin_kill_attaque:
            # Ce bras ne compare PAS le port : il etablit que le NATIF sait faire fire l'ability
            # sur ce porteur, hors crush. C'est la garde de non-degenerescence du bras principal.
            ok = len(live["groupes"]) > 0
            print("[%s] NON-DEGENERESCENCE : le natif ouvre %d groupe(s) `%s` (delta PV %+d, "
                  "defeatedByMelee=%s)"
                  % (m["bras"], len(live["groupes"]), m["rec"]["ability"],
                     (live["hp_apres"] or 0) - (m["rec"]["hp_avant"] or 0),
                     live["defeated_by_melee"]))
            if not ok:
                print("FAUTE : le natif NE FIRE PAS meme hors crush -- l'ability n'est donc pas "
                      "montee sur ce porteur, et le bras principal ne mesure RIEN")
                rc |= 1
            return rc
        if off["mine_vivante"] == mort_live:
            print("REFUS : le CRUSH lui-meme diverge (port mine_vivante=%s, natif=%s) -- les deux "
                  "cotes ne jouent pas le meme pas" % (off["mine_vivante"], live["mine_vivante"]))
            return 2

        nat_fire = len(live["groupes"]) > 0
        port_fire = bool(off["fire"][m["face"]])
        d_live = (live["hp_apres"] or 0) - (rec["hp_avant"] or 0)
        print("[%s] VERDICT : natif fire=%s (%d groupe(s) `%s`, delta PV %+d) | port fire=%s | "
              "defeatedByMelee(natif)=%s"
              % (m["bras"], nat_fire, len(live["groupes"]), rec["ability"], d_live, port_fire,
                 live["defeated_by_melee"]))
        if nat_fire != port_fire:
            print("FAUTE : `%s` -- natif=%s port=%s" % (rec["ability"], nat_fire, port_fire))
            if m["face"] == "dawnblade":
                print("        le conjoint `IsDefeatedByMeleeAttack` lit le marqueur natif "
                      "(`defeatedByMelee`=%s ici) ; le port l'APPROXIME par la POSITION, et apres "
                      "un crush le mover est SUR la tuile du crushe (distance 0 = << melee >>)."
                      % live["defeated_by_melee"])
            rc |= 1
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--face", choices=sorted(FACES), default="haze")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--ennemi1", default="necroWarden")
    ap.add_argument("--ennemi2", default="necroOverlord")
    ap.add_argument("--hp-target", type=int, default=900000)
    ap.add_argument("--hp-player", type=int, default=900000)
    ap.add_argument("--temoin-sans-crush", action="store_true", dest="temoin_sans_crush",
                    help="BRAS TEMOIN : le mover fait le MEME pas vers une tuile LIBRE adjacente. "
                         "Aucun crush -> aucune des deux classes ne doit fire, des deux cotes.")
    ap.add_argument("--temoin-kill-attaque", action="store_true", dest="temoin_kill_attaque",
                    help="BRAS TEMOIN DE NON-DEGENERESCENCE : le mover TUE un ennemi par une "
                         "ATTAQUE (pas un crush). Le natif DOIT alors faire fire l'ability. Sans "
                         "ce bras, un << le natif ne fire pas >> ne distingue pas << le crush ne "
                         "l'arme pas >> de << l'ability n'est pas montee sur ce porteur >>.")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    print("== #462-...-r6-r2 blast radius du CRUSH -- face %s, board %s seed %s%s"
          % (a.face, a.board, a.seed, " [TEMOIN]" if a.temoin_sans_crush else ""))

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    seed_bc = seed_bc_avec_poseur()
    try:
        rc = run(a, rpc, Board, ChargeRegimeHarness, seed_bc)
    finally:
        Path(seed_bc).unlink(missing_ok=True)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
