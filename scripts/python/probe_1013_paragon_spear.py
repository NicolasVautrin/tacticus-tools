#!/usr/bin/env python
"""Probe #1013 -- `ParagonSpear` (relique 1494 de `custoKyrus`), CONFRONTEE LIVE.

CE QUE CE PROBE MESURE, ETAGE PAR ETAGE (jamais un scalaire fitte)

  0. MONTAGE      la relique est-elle MONTEE ? (`unitAbilityStates`, entree de hierarchie **3**),
                  et le PORT l'inscrit-il ? (`collect_triggered_abilities` -> `ParagonSpearAbility`).
                  Sans cet etage, tout ce qui suit mesurerait le vide.
  1. POOL         `GetPossibleTargets()` du PORT, aux trois distances driven -- c'est le
                  DISCRIMINANT de structure : d=1 prend la branche ADJACENTE, d=2 la branche
                  DISTANTE (`range` = 2), d=3 rend le pool VIDE.
  2. NATIF        au `endturn` qui entre dans le turn-start du porteur, le delta de PV des ennemis.
                  d=1 et d=2 : > 0. **d=3 : exactement 0** -- c'est la contre-epreuve GEOMETRIQUE,
                  celle qui etablit que le signal des deux premiers regimes vient bien de CETTE
                  ability et pas d'autre chose au turn-start.
  3. PORT         le MEME turn-start rejoue OFFLINE sur la capture PRE-`endturn`
                  (`start_turn_triggers`), degat compare au natif.
  4. NIVEAU       contre-epreuve MAGNITUDE : `triggered_ability_state` force sur le couple PASSIF
                  (l'etat d'avant #357). Le niveau passif vaut 50 dans tout runner normalise et
                  `AbilityConfiguration$$TryGetVariableArrayForLevel` CLAMPE -> le bras mute lit
                  `minDmg[10]/maxDmg[10]`. Au NIVEAU 1 les deux intervalles sont **DISJOINTS**
                  (`[2155, 2940]` contre `[3202, 4368]` au build courant), donc le bras mute NE PEUT
                  PAS rendre le meme nombre : c'est le seul regime ou les deux hypotheses se
                  separent, et le probe le VERIFIE avant de conclure.
  5. SANS RAIL    `load_state(ability_states=False)` -- l'etat d'AVANT #357 : le port n'inscrit rien,
                  donc 0 event. Sans ce bras, l'etage 3 serait un vert que rien ne fait rougir.

MONTAGE. `custoKyrus` est DANS le pool rank 17 -> etat 2 de la gate relique : `--equip-relic` suffit,
aucune injection catalogue. Il est mis cote **ADVERSAIRE** (`--a-units`) pour que le build demarre au
tour du JOUEUR : on drive alors les positions, puis `endturn` fait ENTRER dans son turn-start, ou
`On(0x16 = TurnStart_Actions)` est emis. `--hp-player` tres haut : les victimes doivent SURVIVRE aux
`nrOfHits = 2` coups, sinon le delta de PV est tronque par la mort.

Reproduire :

    cd scripts/python
    python probe_1013_paragon_spear.py --dist 1          # branche ADJACENTE
    python probe_1013_paragon_spear.py --dist 2          # branche DISTANTE (range = 2)
    python probe_1013_paragon_spear.py --dist 3          # contre-epreuve GEOMETRIQUE (0 attendu)
    python probe_1013_paragon_spear.py --dist 1 --level 3

Sorties dans `logs/` (jamais `data/`). ASCII only (cp1252). Discipline runner : `--state-file`
absolu, un runner a la fois, dispose en sortie.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parents[1]

CARRIER = "custoKyrus"            # ETAT 2 : DANS le pool rank 17 -> `--equip-relic` seul
RELIC = "ParagonSpear"            # `TriggeredAbilityType` 0x5d6 = 1494
RELIC_ID = 1494
#: DEUX victimes : le `First(1)` doit n'en frapper QU'UNE. Le couple est choisi pour que
#: l'`endturn` BASCULE (cf. la garde `turn.switched` dans `run`) -- `orksNob` en tete garde la main
#: au camp joueur sur ce board, et le releve rendrait alors « natif 0 » sans divergence reelle.
VICTIMS = "templAggressor,orksRuntherd"
BOARD = "MC1_67"
SEED = "777"
#: Seeds ESSAYEES DANS L'ORDRE par `run_any` : `rl_duel build` joue le debut de bataille, donc si
#: une victime spawne deja dans le rayon le turn-start du porteur a lieu AVANT toute capture et
#: l'`endturn` d'apres ne le rejoue pas. On ne SUBIT pas ce tirage : on change de bataille.
SEEDS = ("777", "31337", "4321", "1234", "555", "9090")
HP_PLAYER = 500000                # les victimes SURVIVENT aux 2 coups -> delta de PV non tronque
TERTIARY_HIERARCHY = 3            # `AddConfiguredAbilities` : `TryAdd(id, tertiaryState, 3)`

MUTATIONS = ("no-rail", "passive-level")


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _out_dir() -> Path:
    p = _ROOT / "logs" / ("probe_1013-%d" % os.getpid())
    p.mkdir(parents=True, exist_ok=True)
    return p


def build_args(level: int) -> list[str]:
    """Arguments `rl_duel build` du montage (hors `--seed`/`--state-file`).

    `--equip-relic` pose les TROIS ecritures APRES la normalisation -> le niveau joue est EXACTEMENT
    celui demande (`buildNormalizedBC` l'ecraserait a 50 s'il etait pose avant, cf. #237 §4)."""
    return ["--board", BOARD, "--p-units", VICTIMS, "--a-units", CARRIER,
            "--equip-relic", "%s:%s:%d" % (CARRIER, RELIC, level),
            "--hp-player", str(HP_PLAYER)]


def _build_subprocess(level: int, seed: str | None = None) -> int:
    state = _out_dir() / "runner.json"
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", (seed or SEED),
            "--state-file", str(state), *build_args(level)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-800:]))
    return json.loads(state.read_text())["runnerId"]


def _tertiary_rows(rpc, rid: int) -> list:
    """Entrees `TriggeredAbility` de hierarchie 3 (`raw` = 12 x int32 depuis `+0x10` :
    `raw[0]` = `AbilityName`, `raw[10]` = hierarchie ; `level`/`mult` de `+0x20`/`+0x24`)."""
    res = rpc("unitAbilityStates", {"runnerId": rid}, 60) or {}
    out = []
    for u in res.get("units") or []:
        for t in u.get("triggered") or []:
            raw = t.get("raw") or []
            if len(raw) > 10 and raw[10] == TERTIARY_HIERARCHY:
                out.append({"entityId": u.get("entityId"), "abilityId": raw[0],
                            "level": t.get("level"), "mult": t.get("mult")})
    return out


def _patch_passive_level():
    """MUTATION `passive-level` : `ability_attack_params` lit le couple PASSIF au lieu du TERTIAIRE.

    Le foyer patche est `engine.runner.abilities.base.triggered_ability_state` -- l'import y est
    DIFFERE (forme C), donc il est re-resolu a chaque appel et la substitution MORD. C'est l'etat du
    port AVANT #357 sur l'axe MAGNITUDE."""
    from engine.runner.operations.triggers import base as B
    saved = B.triggered_ability_state

    def _passive_only(state, unit_id, ability_name):
        from engine.runner.components import StatsComponent
        e = state.get_entity(unit_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        if ctx is None:
            return (None, 100)
        return (getattr(ctx, "passive_ability_level", None),
                int(getattr(ctx, "ability_variables_multiplier", 100) or 100))
    B.triggered_ability_state = _passive_only
    return lambda: setattr(B, "triggered_ability_state", saved)


def _seed_rng(state, rng_state) -> None:
    """Cale `state.rng` sur l'etat MT CAPTURE (`dumpRng`), pour que le rejeu offline consomme le
    MEME flux que le natif.

    ⚠ SANS ce calage, `AttackDamageOperation.execute_ability_attack` **SKIPPE le degat et rend
    `None`** (garde defensive documentee : « si `state.rng` n'est pas cale, on SKIP au lieu de
    lever »). Le port rendait alors `events = 1`, la BONNE cible... et `delta = 0` : une attaque
    qui n'attaque pas, sans erreur ni trace. C'est exactement le vert-qui-ment que la
    decomposition par etage attrape."""
    from engine.runner.prng import IntBasedMersenneTwister
    if not (isinstance(rng_state, dict) and rng_state.get("mt")):
        return
    rng = IntBasedMersenneTwister()
    rng.mt = list(rng_state["mt"])
    rng.mti = rng_state["mti"]
    state.rng = rng


def _port_turn_start(dv, ob, snap, board, ability_states, carrier_vis: str, rng_state=None) -> dict:
    """Rejoue `On(TurnStart_Actions = 0x16)` OFFLINE sur la capture, pour le joueur du PORTEUR.

    `ability_states=False` = le canal #357 REFUSE -> le rail ne voit pas la relique (etat d'avant).
    ⚠ `False`, PAS `None` : depuis #363 `None` veut dire AUTO, et sous pytest un transport ambiant
    est lie -- un `None` ferait re-tirer le payload par ce bras meme et la contre-epreuve
    deviendrait un vert qui ment."""
    from engine.runner.components import HealthComponent, OwnerComponent, StatsComponent
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    from engine.runner.operations.triggers.dispatch.turn import start_turn_triggers
    from engine.runner.snapshot import load_state

    state = load_state(dv, ob, snap, board=board, ability_states=ability_states)
    _seed_rng(state, rng_state)

    def by_vis(vis):
        for uid, e in state.entities.items():
            sc = e.get_component(StatsComponent)
            if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
                return uid
        return None

    car = by_vis(carrier_vis)
    if car is None:
        return {"error": "porteur absent offline"}
    sc = state.get_entity(car).get_component(StatsComponent)
    oc = state.get_entity(car).get_component(OwnerComponent)
    inscribed = [type(x).__name__ for x in collect_triggered_abilities(state)
                 if getattr(x, "owner_id", None) == car]
    hp0 = {uid: (e.get_component(HealthComponent).hp if e.get_component(HealthComponent) else None)
           for uid, e in state.entities.items()}
    # COMPTE DE TIRAGES du port : l'etage qui dit si un ecart de degat vient du CALCUL ou d'un
    # DESALIGNEMENT du flux. On compte les appels, on ne devine pas.
    from engine.runner.prng import IntBasedMersenneTwister
    draws = {"n": 0}
    origs = {n: getattr(IntBasedMersenneTwister, n) for n in ("next_internal", "next")}

    draws["calls"] = []

    def _wrap(name, fn):
        def traced(self, *a, **kw):
            draws["n"] += 1
            v = fn(self, *a, **kw)
            draws["calls"].append((name, list(a)[:2], v))
            return v
        return traced
    for n, fn in origs.items():
        setattr(IntBasedMersenneTwister, n, _wrap(n, fn))
    try:
        out = start_turn_triggers(state, int(oc.player)) or []
    finally:
        for n, fn in origs.items():
            setattr(IntBasedMersenneTwister, n, fn)
    ev = [e for e in out if isinstance(e, dict) and e.get("ability") == RELIC]
    hp1 = {uid: (e.get_component(HealthComponent).hp if e.get_component(HealthComponent) else None)
           for uid, e in state.entities.items()}
    delta = sum((hp0[k] - hp1[k]) for k in hp0
                if hp0[k] is not None and hp1.get(k) is not None and hp0[k] > hp1[k])
    hit = [k for k in hp0 if hp0[k] is not None and hp1.get(k) is not None and hp1[k] < hp0[k]]
    atk = (ev[0].get("attack") if ev else None) or {}
    # DECOMPOSITION PAR ETAGE : les parametres que `ability_attack_params` rend pour CE porteur,
    # relus SEPAREMENT du resultat de l'attaque. Une divergence se localise ici (bornes / coups /
    # percage) au lieu de se lire comme un scalaire qui ne colle pas.
    from engine.runner.abilities.base import ability_attack_params
    try:
        stage = ability_attack_params(state, car, RELIC, "Bolter", ranged=True,
                                      hits_key="nrOfHits", level_slot="tertiary")
    except Exception as exc:                                  # pragma: no cover - diagnostic
        stage = ("ERR", str(exc)[:160])
    return {"inscribed": inscribed, "events": len(ev), "delta": int(delta), "hit_units": hit,
            "draws": draws["n"], "mti": getattr(getattr(state, "rng", None), "mti", None),
            "draw_calls": draws["calls"],
            "mt_final": list(getattr(getattr(state, "rng", None), "mt", []) or []),
            "stage_params": list(stage), "raw": (ev[0] if ev else None),
            "target": (ev[0].get("target") if ev else None),
            "total": atk.get("total"), "range": (ev[0].get("range") if ev else None),
            "profile": (ev[0].get("profile") if ev else None),
            "tertiary": getattr(sc.ctx, "tertiary_ability", None),
            "level": getattr(sc.ctx, "tertiary_ability_level", None),
            "mult": getattr(sc.ctx, "tertiary_ability_variables_multiplier", None),
            "passive_level": getattr(sc.ctx, "passive_ability_level", None)}


def _port_pool(dv, ob, snap, board, ability_states, carrier_vis: str) -> dict:
    """ETAGE 1 -- `GetPossibleTargets()` du PORT et la BRANCHE prise, sans rien executer."""
    from engine.runner.components import StatsComponent
    from engine.runner.operations.triggers.loki import paragon_spear as PS
    from engine.runner.snapshot import load_state

    state = load_state(dv, ob, snap, board=board, ability_states=ability_states)
    car = None
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == carrier_vis:
            car = uid
    if car is None:
        return {"error": "porteur absent offline"}
    ctx = PS.entities_from_state(state, int(car), owner_id=int(car))
    rng = PS.paragon_spear_range()
    adj = [u["id"] for u in PS.paragon_spear_adjacent_targets().evaluate(ctx) or []]
    far = [u["id"] for u in PS.paragon_spear_ranged_targets(rng).evaluate(ctx) or []]
    pool = [u["id"] for u in PS.paragon_spear_possible_targets(rng).evaluate(ctx) or []]
    return {"range": rng, "adjacent": sorted(adj), "ranged": sorted(far), "pool": sorted(pool),
            "branch": ("adjacent" if adj else ("ranged" if far else "vide"))}


def run_any(rpc, dist: int = 1, level: int = 1, mutate: str | None = None, build_runner=None,
            keep: bool = False, seeds=SEEDS) -> dict:
    """`run` essaye sur PLUSIEURS batailles, et rend la PREMIERE dont le montage tient.

    Le seul motif de re-essai est un montage impossible sur CETTE bataille (turn-start deja joue au
    build, pas de tuile libre a la distance voulue, moins de deux ennemis) -- jamais un desaccord
    de mesure : un releve `ok` est rendu tel quel, meme s'il est rouge. C'est la difference entre
    « changer de bataille » et « chercher celle qui arrange »."""
    last = None
    for seed in seeds:
        r = run(rpc, dist=dist, level=level, mutate=mutate, build_runner=build_runner,
                keep=keep, seed=seed)
        last = r
        if r.get("ok"):
            return r
    return last or {"ok": False, "why": "aucune seed essayee"}


def run(rpc, dist: int = 1, level: int = 1, mutate: str | None = None, build_runner=None,
        keep: bool = False, seed: str | None = None) -> dict:
    """Monte le regime, mesure le natif ET le port, rend le releve. Ne LEVE pas -- l'appelant juge."""
    assert mutate in (None,) + MUTATIONS, "mutation inconnue : %s" % (mutate,)
    import hexgeo
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board

    out: dict = {"dist": dist, "level": level, "mutate": mutate, "seed": (seed or SEED),
                 "ok": False, "why": None}
    out["bounds"] = [int(ability_var(RELIC, "minDmg", level, multiplier_pct=100) or 0),
                     int(ability_var(RELIC, "maxDmg", level, multiplier_pct=100) or 0)]
    out["bounds_clamped"] = [int(ability_var(RELIC, "minDmg", 50, multiplier_pct=100) or 0),
                             int(ability_var(RELIC, "maxDmg", 50, multiplier_pct=100) or 0)]

    rid = (build_runner((seed or SEED), extra=build_args(level))["rid"] if build_runner is not None
           else _build_subprocess(level, seed))
    out["rid"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            out["why"] = "boardGraph indispo"
            return out
        board = Board(bg["tiles"], adjacency="native_sym")

        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
        ov = next((u for u in (dv0.get("units") or []) if u.get("visualId") == CARRIER), None)
        if ov is None:
            out["why"] = "%s absent du build" % CARRIER
            return out
        oid, oplayer = ov["id"], ov.get("owner")
        if dv0.get("currentPlayer") == oplayer:
            out["why"] = "le build demarre au tour du PORTEUR -- `endturn` n'entre plus dans son turn-start"
            return out

        # --- ETAGE 0 : la relique est-elle MONTEE ? -----------------------------------------------
        rows = _tertiary_rows(rpc, rid)
        out["tertiary_rows"] = rows
        mine = [r for r in rows if r["abilityId"] == RELIC_ID]
        if not mine:
            out["why"] = ("aucune entree de hierarchie 3 pour %s (id %d) : la relique n'est PAS "
                          "montee -- le montage #237 a echoue" % (RELIC, RELIC_ID))
            return out
        out["mounted"] = mine[0]

        def live():
            return {u["squadId"]: u
                    for u in (rpc("observeBattle", {"runnerId": rid}, 40).get("units") or [])
                    if not u.get("isDead") and u.get("col") is not None}

        U = live()
        if oid not in U:
            out["why"] = "porteur absent d'observeBattle"
            return out
        # LE TURN-START DU PORTEUR A-T-IL DEJA EU LIEU ? `rl_duel build` joue le debut de bataille :
        # si une victime spawne DEJA dans le rayon, le natif tire AVANT toute capture, et l'`endturn`
        # d'apres ne rejouera pas ce turn-start -- le releve montrerait alors « natif 0 » contre un
        # port qui frappe, c'est-a-dire une divergence FABRIQUEE. On le DIT au lieu de le subir :
        # l'etat MT neuf d'un runner vaut 624 (bloc non encore consomme).
        rng_pre = rpc("dumpRng", {"runnerId": rid}, 30) or {}
        out["rng_pristine"] = (rng_pre.get("mti") == 624)
        hurt = [s for s, u in U.items()
                if u.get("hpMax") is not None and u.get("hp") is not None
                and int(u["hp"]) < int(u["hpMax"])]
        out["already_hurt"] = hurt
        if not out["rng_pristine"]:
            out["why"] = ("le turn-start du porteur a DEJA eu lieu au build (mti=%s, blessees=%s) : "
                          "l'`endturn` ne le rejouera pas -- montage a refaire, PAS une divergence"
                          % (rng_pre.get("mti"), hurt))
            return out
        opos = (U[oid]["col"], U[oid]["row"])
        foes = [s for s, u in U.items() if u.get("teamId") != U[oid].get("teamId")]
        if len(foes) < 2:
            out["why"] = "moins de 2 ennemis vivants -- le `First(1)` ne serait pas discriminant"
            return out

        # --- conduite des positions : UNE victime a `dist` EXACT, les autres HORS de portee --------
        # On CONDUIT -- la geometrie de spawn n'est jamais une raison de ne pas mesurer.
        occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
        placed = []
        for k, fid in enumerate(sorted(foes)):
            want = dist if k == 0 else max(4, dist + 2)     # 1 seule a `dist`, les autres au large
            cands = [t for t in board.by_id
                     if board.walkable(t) and t not in occupied
                     and hexgeo.distance(opos, board.coord(t)) == want]
            if not cands:
                out["why"] = "aucune tuile libre a d=%d du porteur" % want
                return out
            tgt = sorted(cands)[0]
            c, r = board.coord(tgt)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": fid, "to": {"col": c, "row": r}}}, 90)
            occupied.discard(board.id_at(U[fid]["col"], U[fid]["row"]))
            occupied.add(tgt)
            placed.append((fid, want))
        U = live()
        dists = {s: hexgeo.distance(opos, (u["col"], u["row"])) for s, u in U.items() if s in foes}
        out["geometry"] = {"carrier": opos, "dists": dists, "wanted": dict(placed)}
        if sorted(dists.values())[0] != dist:
            out["why"] = ("montage NON obtenu : la plus proche est a d=%d, voulu d=%d"
                          % (sorted(dists.values())[0], dist))
            return out

        # --- capture PRE-`endturn` (positions FINALES) --------------------------------------------
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        uas = rpc("unitAbilityStates", {"runnerId": rid}, 60)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)          # etat MT AVANT le turn-start natif
        out["rng_captured"] = bool(isinstance(rng0, dict) and rng0.get("mt"))

        # --- ETAGE 1 + 3 + 4 + 5 : le PORT, quatre lectures de la MEME capture ---------------------
        out["pool"] = _port_pool(dv, ob, snap, board, uas, CARRIER)
        undo = _patch_passive_level() if mutate == "passive-level" else (lambda: None)
        try:
            out["port"] = _port_turn_start(dv, ob, snap, board,
                                           False if mutate == "no-rail" else uas, CARRIER, rng0)
        finally:
            undo()
        out["port_no_rail"] = _port_turn_start(dv, ob, snap, board, False, CARRIER, rng0)
        undo = _patch_passive_level()
        try:
            out["port_passive_level"] = _port_turn_start(dv, ob, snap, board, uas, CARRIER, rng0)
        finally:
            undo()

        # --- ETAGE 2 : le NATIF, delta de PV des ennemis sur CE seul turn-start --------------------
        hp0 = {s: u["hp"] for s, u in U.items()}
        # `endturn` TERMINE L'UNITE COURANTE, pas l'equipe : il en faut autant que le camp joueur
        # a d'unites encore a finir avant que la main passe au porteur. On BOUCLE donc jusqu'a la
        # bascule au lieu d'en jouer un seul et de lire « natif 0 ». Aucun de ces tours ne fait
        # AGIR une unite du joueur (on ne lui demande rien), donc le seul degat de la sequence
        # reste celui du turn-start du porteur -- ce que le releve `rng` verifie ensuite.
        ack = None
        for _ in range(8):
            ack = rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                                      "captureEvents": True}, 120)
            cur = (rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 120) or {}).get("currentPlayer")
            out["turn_hops"] = int(out.get("turn_hops", 0)) + 1
            if cur == oplayer:
                break
        # LE TOUR A-T-IL BASCULE SUR LE PORTEUR ? Sans ce controle, un `endturn` qui ne rend PAS la
        # main a l'adversaire se lit comme « le natif n'a rien inflige » -- une divergence
        # FABRIQUEE par le montage. Mesure #1013 : quand la victime spawne DEJA dans le rayon, le
        # turn-start du porteur a lieu AU BUILD (avant toute capture), et l'`endturn` suivant ne
        # rejoue pas ce meme turn-start.
        dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 120)
        out["turn"] = {"player_before": dv0.get("currentPlayer"),
                       "player_after": dv2.get("currentPlayer"), "carrier_player": oplayer,
                       "switched": dv2.get("currentPlayer") == oplayer}
        if not out["turn"]["switched"]:
            # MESURE #1013 : un `endturn` qui ne bascule pas (le camp joueur garde la main) rend
            # « natif 0 » -- indiscernable d'un trigger qui refuse, alors que le turn-start du
            # porteur n'a tout simplement PAS eu lieu. Vu en vrai : meme board, meme seed, meme
            # geometrie, seule la composition du camp joueur change (`orksNob` ne bascule pas,
            # `templAggressor` oui) et le verdict passe de ECART a ACCORD BIT-EXACT. On REFUSE le
            # montage au lieu d'en tirer une divergence.
            out["why"] = ("l'`endturn` n'a pas rendu la main au porteur (joueur %s -> %s, porteur "
                          "%s) : le turn-start natif n'a PAS eu lieu -- montage a refaire, PAS une "
                          "divergence" % (dv0.get("currentPlayer"), dv2.get("currentPlayer"), oplayer))
            return out
        # DECOMPOSITION du cote NATIF : les events du turn-start, coup par coup. Un total qui ne
        # colle pas se localise ici (nombre de coups, crit, armure) au lieu d'etre un scalaire.
        evs = (ack or {}).get("events") if isinstance(ack, dict) else None
        out["native_events"] = [e for e in (evs or [])
                                if isinstance(e, dict)
                                and str(e.get("type", "")).lower().find("damage") >= 0][:12]
        out["native_event_types"] = sorted({str(e.get("type")) for e in (evs or [])
                                            if isinstance(e, dict)})[:24]
        post = {u["squadId"]: u for u in (rpc("observeBattle", {"runnerId": rid}, 40)
                                          .get("units") or [])}
        hp1 = {s: (post.get(s) or {}).get("hp") for s in hp0}
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        # ALIGNEMENT DU FLUX : `mti` AVANT / APRES le turn-start natif, contre le `mti` du port sur
        # la MEME capture. Egaux -> le port consomme le meme nombre de tirages ; differents -> tout
        # ecart de degat est un DESALIGNEMENT, pas une erreur d'arithmetique.
        out["rng"] = {"mti_before": (rng0 or {}).get("mti"), "mti_after_native": (rng1 or {}).get("mti"),
                      "mti_after_port": out["port"].get("mti"), "port_draws": out["port"].get("draws"),
                      # LE test decisif : le tableau MT FINAL des deux cotes. Egal -> les MEMES
                      # tirages, dans le MEME ordre -> tout ecart de degat est ARITHMETIQUE.
                      "mt_final_equal": bool(list((rng1 or {}).get("mt") or [])
                                             == list(out["port"].get("mt_final") or [])),
                      "draw_calls": out["port"].get("draw_calls")}
        out["port"].pop("mt_final", None)                      # volumineux : hors du releve
        out["hp"] = {"before": hp0, "after": hp1}
        out["native_delta"] = int(sum((hp0[s] - hp1[s]) for s in hp0
                                      if hp1.get(s) is not None and hp1[s] < hp0[s]))
        out["native_hit"] = sorted(s for s in hp0 if hp1.get(s) is not None and hp1[s] < hp0[s])
        out["ok"] = True
        return out
    finally:
        if not keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 40)
            except Exception:                                     # pragma: no cover - diagnostic
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description="#1013 -- ParagonSpear (relique 1494)")
    ap.add_argument("--dist", type=int, default=1, help="distance hex EXACTE de la victime la plus proche")
    ap.add_argument("--level", type=int, default=1, help="niveau de la RELIQUE (1 ou 3 -- pas 50)")
    ap.add_argument("--mutate", choices=MUTATIONS)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, dist=a.dist, level=a.level, mutate=a.mutate, keep=a.keep)
    print("runner=%s dist=%s level=%s mutate=%s ok=%s why=%s"
          % (r.get("rid"), r.get("dist"), r.get("level"), r.get("mutate"), r.get("ok"), r.get("why")))
    print("bornes minDmg/maxDmg[%s] = %s   (ce que le niveau PASSIF clampe rendrait = %s)"
          % (a.level, r.get("bounds"), r.get("bounds_clamped")))
    if not r.get("ok"):
        return 1
    print("monte  : %s" % (r.get("mounted"),))
    print("geom   : %s" % (r.get("geometry"),))
    print("[POOL port] %s" % (r.get("pool"),))
    print("[PORT avec rail] %s" % (r.get("port"),))
    print("[PORT sans rail] events=%s delta=%s"
          % (r["port_no_rail"].get("events"), r["port_no_rail"].get("delta")))
    print("[PORT niveau PASSIF] events=%s delta=%s total=%s"
          % (r["port_passive_level"].get("events"), r["port_passive_level"].get("delta"),
             r["port_passive_level"].get("total")))
    print("[RNG] %s" % (r.get("rng"),))
    print("[NATIF] delta PV ennemis = %s | touchees = %s"
          % (r.get("native_delta"), r.get("native_hit")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
