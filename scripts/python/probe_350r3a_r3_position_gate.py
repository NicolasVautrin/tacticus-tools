#!/usr/bin/env python
"""#350-r3a-r3 -- le gate d'ELIGIBILITE d'une cible : PAR POSITION, et les deux modeles SEPARENT-ILS ?

LA QUESTION BINAIRE
-------------------
« Le gate d'eligibilite d'une cible est-il evalue PAR POSITION par le natif, la ou le port l'evalue
autrement -- et existe-t-il un montage ou les deux modeles rendent des ARGMAX DIFFERENTS ? »

Un montage ou les deux modeles rendent le MEME argmax ne conclut RIEN. C'est arrive DEUX FOIS sur ce
residu (le releve de #356, puis le `0/33` du WIP herite) : les deux mesuraient un ecart de COMPTE
d'eligibilite a une position, jamais un ecart de DECISION.

CE QUE LE DECOMPILE DIT (lu VERBATIM, `rnca9r7q6c`)
--------------------------------------------------
`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable(this, caster, possibleCasterTile)` :

    UnitPosition pos = new UnitPosition(possibleCasterTile)
    raw = <IBattleQuery> slot 0x42 . GetValidTargets(caster, pos, this+0x10 /* abilityType */)
    targets = raw+0x10                                  # ValidTargets.AllTargets
    ListExtensions.Remove(targets, Predicate(this, <GetEligibleTargetsEntities>b__58_0))
    foreach entity in targets: AbilityEntities{ +0x40 possibleCasterTile, ... }

=> l'eligibilite native est bien evaluee PAR POSITION : une passe de
`IdunBattle.Core.Services.AttackQuery$$GetValidTargets(unit, UnitPosition(P), ability)` par position
candidate. Le predicat de `Remove` est
`IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluateTarget` (`!(IsUnit && CurrentOwnerIsEnvironment)
&& !IsIrrelevantObject`) : il ne retire pas un ennemi ordinaire.

Cote port, `_PlanTargetPlaybook.generate_candidates` gate sur `P in ranked(tgt)`, ou `ranked(tgt)`
sort de `decisionView.attackPlans`. Ce plan est bati par `computeAttackPlans`
(`frida/hooks/features/ai-step/projection.ts`) en shrink-and-recall sur
`IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom`, dont le corps garde une tuile ssi
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason(unit, UnitPosition(tile), target,
ability)` n'est pas invalide.

L'ENONCE HERITE (« le port gate sur une UNION de positions ») est donc FAUX sur le mecanisme : les
DEUX cotes sont per-position. Restent DEUX ecarts STRUCTURELS, et ce probe les separe :

  (E1) le PREDICAT -- `GetValidTargets` (`GetInvalidCasterReason` + masque `TargetingOptions` +
       boucle `GetInvalidTargetReason`) contre `GetInvalidTargetReason` SEUL ;
  (E2) la TRONCATURE -- `computeAttackPlans` ne garde que les `maxRank` MEILLEURES tuiles par paire
       (`for (let r = 0; r < maxRank; r++)`, defaut 8, `decisionView` defaut 6). Au-dela, le port
       perd des positions VALIDES. C'est un ecart a sens UNIQUE (port plus PAUVRE) et il est
       invisible tant que `movableCount <= maxRank`.

LES CANAUX (tous DEJA deployes -- aucune reinjection, aucun capteur neuf)
------------------------------------------------------------------------
* `ncPlaybookPredict` (`--col/--row`) = le NATIF a une position ARBITRAIRE. Il rend DEUX choses :
  `captured` (un `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor` par cible ELIGIBLE a cette
  position -- 1202 n'a aucun gate predictif intermediaire) ET `bucketUtil`/`bucketAction`, c.-a-d.
  **l'ARGMAX QUE LE NATIF LUI-MEME attribue a cette position**. L'argmax natif global n'est donc pas
  reconstruit : il est MESURE.
* le PORT : `VigilanceEternalPlaybook.generate_candidates(ctx)` -- le VRAI code livre, pas une
  re-implementation du gate dans le probe.
* `castFromTiles` = `AttackQuery.GetInvalidTargetReason(caster, tile, target, ability)` tuile par
  tuile : LITTERALEMENT le predicat de `GetBestTileToAttackFrom`, donc l'ensemble des tuiles valides
  AVANT troncature. Comparer `ranked(tgt)` a `castFromTiles(tgt)` isole (E2) ; comparer
  `castFromTiles(tgt)` a l'eligibilite native isole (E1).
* `abilityTargets.fromHere` = `GetValidTargets` a la position COURANTE : recoupe le premier canal.

DISCIPLINE : ASCII strict en sortie (CLAUDE.md), symboles jamais des VA, board CHOISI, state-file
absolu sous `logs/`, runners disposes dans un `finally`.

Usage (depuis scripts/python) :
    python probe_350r3a_r3_position_gate.py --fixture carte
    python probe_350r3a_r3_position_gate.py --fixture separation
    python probe_350r3a_r3_position_gate.py --sweep          # balaie les geometries
    python probe_350r3a_r3_position_gate.py --fixture carte --max-rank 6
Codes de retour : 0 = mesure faite ; 1 = montage KO (rien n'a ete confronte).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

_ABILITY = 1202          # ActiveAbilityType.VigilanceEternal
_CASTER = "custoKyrus"   # Tyrith -- porteur lineup de 1202, present au seed BC


# --- FIXTURES NOMMEES (jamais de montage inline) ------------------------------------------------

# `rings` = la distance hex EXACTE a laquelle chaque ennemi est POSE autour du caster. C'est le
# levier de pilotage : la geometrie est CHOISIE, jamais subie (cf. feedback drive-positions).
_FIXTURES = {
    # Montage 1 -- LA CARTE. Un ennemi au contact, un a portee de charge : on lit, position par
    # position, l'ensemble des cibles que chaque modele declare eligibles.
    "carte": {
        "name": "carte", "board": "MC1_67", "seed": 35041, "rank": 17,
        "caster": _CASTER, "ability": _ABILITY,
        "p_units": "custoKyrus,astraBullgryn", "a_units": "necroWarden,ultraTitus",
        "center": (3, 4), "rings": {"necroWarden": 1, "ultraTitus": 3},
        "level": 50, "mult": 140, "max_rank": 32,
    },
    # Montage 2 -- LA SEPARATION. Meme squelette, l'ennemi de plus haute utilite pose HORS de portee
    # de charge : s'il reste dans `ranked(tgt)` cote port alors que le natif le refuse partout, les
    # argmax divergent.
    "separation": {
        "name": "separation", "board": "MC1_67", "seed": 35042, "rank": 17,
        "caster": _CASTER, "ability": _ABILITY,
        "p_units": "custoKyrus,astraBullgryn", "a_units": "necroWarden,ultraTitus",
        "center": (3, 4), "rings": {"necroWarden": 1, "ultraTitus": 5},
        "level": 50, "mult": 140, "max_rank": 32,
    },
    # Montage 3 -- LA TRONCATURE (E2). Meme geometrie que `carte`, mais `max_rank` volontairement
    # BAS : `ranked(tgt)` est alors un SOUS-ENSEMBLE strict des tuiles valides, et le port perd des
    # positions que le natif accepte.
    "troncature": {
        "name": "troncature", "board": "MC1_67", "seed": 35043, "rank": 17,
        "caster": _CASTER, "ability": _ABILITY,
        "p_units": "custoKyrus,astraBullgryn", "a_units": "necroWarden,ultraTitus",
        "center": (3, 4), "rings": {"necroWarden": 1, "ultraTitus": 2},
        "level": 50, "mult": 140, "max_rank": 2,
    },
    # Montage 4 -- GENERALISATION A UNE AUTRE SOUS-CLASSE. `1153 HammerOfWrath`
    # (`bloodIntercessor`, present au pool) est l'autre `_PlanTargetPlaybook` a utilite
    # POSITION-DEPENDANTE (une charge, comme 1202) : c'est donc la seule ou le gate per-position
    # peut deplacer l'argmax. Les quatre autres (BloodyFury, Stormcaller, VexillaMagnifica,
    # BlackRage) ont une utilite position-INDEPENDANTE -> leur argmax est l'ORIGINE par keep-first,
    # que le gate soit tronque ou non : le fix ne peut pas les changer, et le dire est une mesure,
    # pas une esperance.
    "hammer": {
        "name": "hammer", "board": "MC1_67", "seed": 35044, "rank": 17,
        "caster": "bloodIntercessor", "ability": 1153,
        "p_units": "bloodIntercessor,astraBullgryn", "a_units": "necroWarden,ultraTitus",
        "center": (3, 4), "rings": {"necroWarden": 1, "ultraTitus": 3},
        "level": 50, "mult": 140, "max_rank": 32,
    },
}


# --- plomberie RPC -------------------------------------------------------------------------------

def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc          # noqa: E402
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=90):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, fx: dict) -> int:
    """`rl_duel build` -- board CHOISI, `--no-ai` (aucun driver natif : chaque deplacement est le
    notre), niveau/multiplicateur d'ability PILOTES par `--unit-stat`."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(fx["seed"]),
           "--state-file", str(state_file), "--board", fx["board"], "--rank", str(fx["rank"]),
           "--p-units", fx["p_units"], "--a-units", fx["a_units"],
           "--unit-stat", "%s:ActiveAbilityLevel=%d,AbilityVariablesMultiplierPercentage=%d"
                          % (fx["caster"], fx["level"], fx["mult"]),
           "--crit", "0,0", "--block-target", "0,0", "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _observe(rpc, sid, rid) -> dict:
    return _r(rpc, sid, "observeBattle", {"runnerId": rid}, 120)


def _alive(o: dict) -> list:
    return [u for u in (o.get("units") or []) if not u.get("isDead")]


def _move(rpc, sid, rid, uid, col, row):
    return _r(rpc, sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _endturn(rpc, sid, rid):
    return _r(rpc, sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _board(rpc, sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = _r(rpc, sid, "boardGraph", {"runnerId": rid}, 60)
    return Board(bg["tiles"], adjacency="evenq")


# --- MONTAGE : geometrie DRIVEE, puis un tour complet pour rendre le mouvement au caster ---------

def _ring_tiles(board, center, dist: int, occupied: set) -> list:
    """Les tuiles WALKABLE a distance hex EXACTE `dist` du centre, ordre deterministe, moins celles
    deja occupees."""
    import hexgeo
    out = []
    for tid, t in board.by_id.items():
        c = (t["col"], t["row"])
        if hexgeo.distance(center, c) != dist:
            continue
        if c in occupied or not board.walkable(tid):
            continue
        out.append(c)
    return sorted(out)


def _stage(rpc, sid, rid, fx: dict, verbose: bool = True) -> dict:
    """Pose la geometrie VOULUE, puis rend son mouvement au caster.

    Trois temps, et le troisieme n'est pas cosmetique :
      1. mon tour -- le caster va au centre, l'allie s'ecarte ;
      2. tour adverse -- chaque ennemi va sur son anneau (`fx["rings"]`) ;
      3. `endturn` -> mon tour SUIVANT : le caster retrouve ses tuiles de move (sans quoi le sweep
         de positions serait reduit a l'origine) et `turnsStarted` vaut 2, donc le gate natif
         `IdunBattle.AI.Playbook.Loki.VigilanceEternalPlaybook$$ShouldEvaluate` (`GetStat(unit,
         0xc) > 1`) est franchi lui aussi.
    """
    import hexgeo
    board = _board(rpc, sid, rid)
    center = tuple(fx["center"])
    o = _observe(rpc, sid, rid)
    us = _alive(o)
    by_vis = {u.get("visualId"): u for u in us}
    caster = by_vis.get(fx["caster"])
    if caster is None:
        return {"ok": False, "error": "caster %s absent du build" % fx["caster"]}
    cid = int(caster["squadId"])
    my_team = caster.get("teamId")
    my_pid = caster.get("playerId")

    # 1. mon tour -- caster au centre, allie repousse loin (il ne doit occuper aucun anneau utile).
    if o.get("currentPlayer") != my_pid:
        _endturn(rpc, sid, rid)
        o = _observe(rpc, sid, rid)
    occupied = {center}
    _move(rpc, sid, rid, cid, *center)
    ally_far = _ring_tiles(board, center, 6, occupied)
    for u in us:
        if u.get("teamId") == my_team and int(u["squadId"]) != cid and ally_far:
            _move(rpc, sid, rid, int(u["squadId"]), *ally_far[0])
            occupied.add(ally_far[0])
            ally_far = ally_far[1:]
    _endturn(rpc, sid, rid)

    # 2. tour adverse -- chaque ennemi sur son anneau.
    placed = {}
    o = _observe(rpc, sid, rid)
    for u in _alive(o):
        if u.get("teamId") == my_team:
            continue
        vis = u.get("visualId")
        d = int((fx.get("rings") or {}).get(vis, 2))
        cands = _ring_tiles(board, center, d, occupied)
        if not cands:
            return {"ok": False, "error": "anneau %d vide autour de %s" % (d, center)}
        _move(rpc, sid, rid, int(u["squadId"]), *cands[0])
        occupied.add(cands[0])
        placed[vis] = cands[0]
    _endturn(rpc, sid, rid)

    # 3. mon tour SUIVANT : mouvement rendu, turnsStarted = 2.
    o = _observe(rpc, sid, rid)
    if o.get("currentPlayer") != my_pid:
        _endturn(rpc, sid, rid)
        o = _observe(rpc, sid, rid)
    us = _alive(o)
    caster = next((u for u in us if int(u["squadId"]) == cid), None)
    if caster is None:
        return {"ok": False, "error": "caster mort pendant le montage"}
    foes = [{"id": int(u["squadId"]), "vis": u.get("visualId"), "pos": (u["col"], u["row"])}
            for u in us if u.get("teamId") != my_team]
    here = (caster["col"], caster["row"])
    if verbose:
        print("  [montage %s] caster %s u%d en %s ; ennemis %s"
              % (fx["name"], fx["caster"], cid, here,
                 [(f["vis"], f["pos"], hexgeo.distance(here, f["pos"])) for f in foes]))
    return {"ok": True, "casterId": cid, "here": here, "foes": foes,
            "placed": placed, "currentPlayer": o.get("currentPlayer")}


# --- LES DEUX MODELES, POSITION PAR POSITION -----------------------------------------------------

def _view(rpc, sid, rid, max_rank: int) -> dict:
    return _r(rpc, sid, "decisionView",
              {"runnerId": rid, "allAbilities": True, "maxRank": int(max_rank)}, 180)


def _reach(rpc, sid, rid, cid: int, dv: dict) -> tuple:
    """`ctx.reach_nc` : la position COURANTE en tete, puis les tuiles de move dans l'ordre natif
    (`IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` seede son OrderedSet
    avec `GetUnitPosition(unit)` avant `UnionWith(movable)`)."""
    mv = _r(rpc, sid, "aiMovableTiles", {"runnerId": rid, "unitId": cid}, 120)
    tiles = []
    for e in (mv.get("units") or []):
        if int(e.get("unitId", -1)) == cid:
            tiles = [(t["col"], t["row"]) for t in (e.get("tiles") or [])]
    me = next((u for u in (dv.get("units") or []) if int(u.get("id", -1)) == cid), None)
    origin = (me["pos"]["col"], me["pos"]["row"]) if me and me.get("pos") else None
    out = ([origin] if origin else []) + [t for t in tiles if t != origin]
    return out, origin


def _port_ranked(dv: dict, cid: int, ability: int) -> dict:
    """LE MODELE DU PORT, lu a la source qu'il consomme : `{targetId: set(tuiles rankees)}` de
    `decisionView.attackPlans` -- exactement ce que `_PlanTargetPlaybook.generate_candidates`
    interroge par `P in rset`."""
    plan = next((p for p in (dv.get("attackPlans") or [])
                 if int(p.get("unitId", -1)) == cid), {}) or {}
    out = {}
    for ev in (plan.get("evals") or []):
        if int(ev.get("abilityId", -1)) != int(ability) or not ev.get("rankCount"):
            continue
        rset = {(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
                if rk.get("col") is not None}
        if rset:
            out[int(ev.get("targetId"))] = rset
    return out


def _native_map(rpc, sid, rid, cid: int, ability: int, positions: list,
                verbose: bool = True) -> dict:
    """LE MODELE DU NATIF, position par position. `targets` = les cibles que
    `GetEligibleTargetsSelectable` a retenues A CETTE POSITION (un `ProbableDamageEvent` par cible,
    1202 n'ayant aucun gate predictif intermediaire) ; `bucketUtil` = l'utilite que le natif attribue
    LUI-MEME a cette position -- son argmax est donc MESURE, pas reconstruit.

    WARN `bucketAction.targetLow` est le dword BAS d'un POINTEUR d'entite, pas un `unitId` (mesure
    #362, `case-350r3-oracle-noncomparable.md` sec.8.5) : publie pour diagnostic, il n'identifie RIEN
    offline. La cible native se lit sur les events CAPTURES (`targets`)."""
    out = {}
    for p in positions:
        r = _r(rpc, sid, "ncPlaybookPredict",
               {"runnerId": rid, "unitId": int(cid), "abilityType": int(ability),
                "via": "evaluate", "col": int(p[0]), "row": int(p[1])}, 240)
        ev = r.get("captured") or []
        ba = r.get("bucketAction") or {}
        out[p] = {"targets": [e.get("targetId") for e in ev],
                  "events": ev, "bucketUtil": r.get("bucketUtil"),
                  "bucketTargetLow": ba.get("targetLow"), "bucket": r.get("bucket"),
                  "error": r.get("error")}
        if verbose:
            print("    P=%-8s natif: cibles=%-14s bucketUtil=%s%s"
                  % (str(p), str(out[p]["targets"]), out[p]["bucketUtil"],
                     (" ERR=%s" % r.get("error")) if r.get("error") else ""))
    return out


def _cast_from_tiles(rpc, sid, rid, cid, tid, ability) -> dict:
    """Le PREDICAT du port SANS troncature : `AttackQuery.GetInvalidTargetReason(caster, tile,
    target, ability)` tuile par tuile. Comparer a `ranked(tgt)` isole la TRONCATURE (E2) ; comparer
    a l'eligibilite native isole le PREDICAT (E1)."""
    r = _r(rpc, sid, "castFromTiles",
           {"runnerId": rid, "casterId": int(cid), "targetId": int(tid),
            "abilityType": int(ability)}, 180)
    return {"currentValid": r.get("currentValid"),
            "moveTiles": [(t["col"], t["row"]) for t in (r.get("moveTiles") or [])]}


# --- LE PORT REEL (pas une re-implementation du gate dans le probe) ------------------------------

def _port_candidate(rpc, sid, rid, cid: int, dv: dict, ability: int) -> dict:
    """Fait tourner `<X>Playbook.generate_candidates` sur un `NCContext` bati par le chemin de
    PRODUCTION (`engine.ai.context.build`) -- c'est le code LIVRE qui decide, pas une copie du gate
    ecrite pour le probe."""
    from engine import weights as W
    from engine.ai import context as AICTX
    from engine.playbook import scene as _scene
    from engine.playbook import noncomparable as NC

    rpc2 = lambda m, b, t=60: _r(rpc, sid, m, b, t)                       # noqa: E731
    mov = _r(rpc, sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
    ctx = AICTX.build(rpc2, rid, dv, mov_by_unit, int(cid), W.load(),
                      _scene.build_predictor(rpc2, rid))
    nc = NC.NCContext(
        uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
        enemies=ctx.enemies, neigh_by_pos=ctx.neigh_by_pos, walkable_by_pos=ctx.walkable_by_pos,
        plan=ctx.plans.get(ctx.uid) or {}, plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id,
        elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets, wt=ctx.wt,
        is_temporary_by_pos=ctx.is_temporary_by_pos, effects_by_pos=ctx.effects_by_pos,
        obs_units=ctx.obs_units, tile_id_by_pos=ctx.tile_id_by_pos,
        active_levels=ctx.active_ability_levels, ability_config=ctx.heal_config,
        units=ctx.units, cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene, debug=False)
    pb = NC.PLAYBOOKS.get(int(ability))
    if pb is None:
        return {"ok": False, "error": "aucun playbook porte pour %d" % ability}
    if not pb.should_evaluate(nc):
        return {"ok": True, "gated": True, "cands": [], "eff": {}}
    cands = pb.generate_candidates(nc)
    # La carte EFFECTIVE du gate porte : `{targetId: positions}` telle que `generate_candidates` la
    # consomme. C'est ELLE qu'il faut confronter au natif -- pas `ranked` du plan, qui n'est que
    # l'une des sources possibles. Mesurer `ranked` a la place aurait rendu le probe aveugle a tout
    # fix du gate (c'est exactement ce qui l'a fait rougir apres coup).
    eff = {}
    for ev in ((nc.plan or {}).get("evals") or []):
        if ev.get("abilityId") != int(ability) or not ev.get("rankCount"):
            continue
        rset = {(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
                if rk.get("col") is not None}
        if rset:
            eff[int(ev.get("targetId"))] = pb.eligible_positions(nc, ev.get("targetId"), rset)
    return {"ok": True, "gated": False, "cands": cands, "reach": list(nc.reach_nc), "eff": eff}


# --- L'ARGMAX NATIF, MESURE (jamais reconstruit) -------------------------------------------------

def _native_argmax(positions: list, nat: dict) -> dict:
    """`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` SEED le
    1er ajoute puis ne remplace QUE si STRICTEMENT superieur -> keep-first au tie, dans l'ordre de
    `reach_nc` (origine en tete). On applique cette regle aux `bucketUtil` MESURES."""
    best = None
    for p in positions:
        u = nat.get(p, {}).get("bucketUtil")
        if u is None:
            continue
        if best is None or u > best[1]:
            best = (p, u, nat[p].get("targets") or [], nat[p].get("bucketTargetLow"))
    if best is None:
        return {"pos": None, "util": None, "targets": [], "targetLow": None}
    return {"pos": list(best[0]), "util": best[1], "targets": best[2], "targetLow": best[3]}


# --- etape 1 : LA CARTE + LES DEUX ARGMAX --------------------------------------------------------

def step1(rpc, sid, logs: Path, fx: dict, verbose: bool = True) -> dict:
    """UN montage, N valeurs de `maxRank`.

    Le NATIF ne connait pas `maxRank` : sa carte d'eligibilite est mesuree UNE fois. Seul le PORT en
    depend (`computeAttackPlans` tronque a `maxRank`). Balayer les rangs sur le MEME etat -- plutot
    qu'un build par rang -- est donc a la fois moins couteux et plus rigoureux : la geometrie est
    EXACTEMENT la meme, l'ecart ne peut venir que du rang."""
    sf = logs / ("p350r3a_r3_%s.json" % fx["name"])
    ranks = tuple(fx.get("ranks") or (fx["max_rank"],))
    rid = None
    try:
        rid = _build(sf, fx)
        st = _stage(rpc, sid, rid, fx, verbose)
        if not st.get("ok"):
            return {"ok": False, "error": st.get("error")}
        cid = st["casterId"]
        dv0 = _view(rpc, sid, rid, max(ranks))
        positions, origin = _reach(rpc, sid, rid, cid, dv0)
        if verbose:
            print("  reach = %d positions (origine %s en tete) ; rangs balayes %s"
                  % (len(positions), origin, list(ranks)))
        nat = _native_map(rpc, sid, rid, cid, fx["ability"], positions, verbose)
        cft = {int(f["id"]): _cast_from_tiles(rpc, sid, rid, cid, f["id"], fx["ability"])
               for f in st["foes"]}
        at = _r(rpc, sid, "abilityTargets",
                {"runnerId": rid, "unitId": int(cid), "abilityType": int(fx["ability"])}, 120)
        from_here, union = [], []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if int(a.get("abilityId", -1)) != int(fx["ability"]):
                    continue
                from_here = [t.get("targetId") for t in (a.get("fromHere") or [])]
                union = [t.get("targetId") for t in (a.get("targets") or [])]
        reasons = {}
        for f in st["foes"]:
            rr = _r(rpc, sid, "abilityReason",
                    {"runnerId": rid, "casterId": int(cid), "abilityType": int(fx["ability"]),
                     "targetId": int(f["id"])}, 60)
            tr = rr.get("targetReason") or {}
            reasons[f["id"]] = {"hex": tr.get("hex"), "reasons": tr.get("reasons")}
        nat_arg = _native_argmax(positions, nat)
        by_rank = []
        for mr in ranks:
            dv = dv0 if mr == max(ranks) else _view(rpc, sid, rid, mr)
            by_rank.append(_one_rank(rpc, sid, rid, cid, fx, dv, mr, positions, origin,
                                     nat, cft, nat_arg, verbose))
    finally:
        if rid is not None:
            _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 30)

    sep = [x for x in by_rank if x["separates"]]
    out = {"ok": True, "fixture": fx["name"], "casterId": cid, "origin": list(origin or ()),
           "foes": st["foes"], "positions": len(positions), "byRank": by_rank,
           "argmaxNative": nat_arg, "separatingRanks": [x["maxRank"] for x in sep],
           "separates": bool(sep),
           "fromHere": from_here, "union": union, "abilityReason": reasons,
           "castFromTiles": {str(k): v for k, v in cft.items()},
           # compat mono-rang (le dernier rang balaye) -- le sweep lit ces cles
           "maxRank": by_rank[-1]["maxRank"], "rows": by_rank[-1]["rows"],
           "divergentPositions": by_rank[-1]["divergentPositions"],
           "e1_predicat": by_rank[-1]["e1_predicat"], "e2_troncature": by_rank[-1]["e2_troncature"],
           "argmaxPort": by_rank[-1]["argmaxPort"]}
    if verbose:
        print("\n  [recoupement origine] fromHere(GetValidTargets)   = %s" % from_here)
        print("                        natif(origine) via oracle  = %s"
              % sorted(set(x for x in (nat[positions[0]]["targets"] or []) if x is not None)))
        print("                        union(mouvement inclus)    = %s" % union)
        for tid, rz in reasons.items():
            print("  abilityReason(tgt=%s) depuis l'origine : hex=%s %s"
                  % (tid, rz["hex"], rz["reasons"]))
        print("\n  ARGMAX NATIF (bucketUtil mesure, keep-first origine d'abord) : %s" % nat_arg)
        for x in by_rank:
            print("  maxRank=%-3d ranked=%-20s gateDiv=%-3d permissif=%-3d splash=%-3d E2plan=%-3d "
                  "port=%s  %s"
                  % (x["maxRank"], x["rankedSizes"], x["divergentPositions"], x["e1_cft_only"],
                     x["e1_nat_only"], x["e2_troncature"], x["argmaxPort"],
                     "SEPARE" if x["separates"] else "coincide"))
    return out


def _one_rank(rpc, sid, rid, cid, fx, dv, mr, positions, origin, nat, cft, nat_arg,
              verbose: bool) -> dict:
    """La carte du PORT a un `maxRank` donne + son argmax, confrontes au natif deja mesure.

    TROIS cartes, et les confondre est precisement l'erreur a ne pas commettre :
      `ranked`        -- ce que `decisionView.attackPlans` CONTIENT (tronque a `maxRank`) ;
      `port`          -- ce que le gate LIVRE consomme (`_PlanTargetPlaybook.eligible_positions`) ;
      `castFromTiles` -- le predicat natif `GetInvalidTargetReason` tuile par tuile, SANS troncature.
    """
    port_rk = _port_ranked(dv, cid, fx["ability"])
    port = _port_candidate(rpc, sid, rid, cid, dv, fx["ability"])
    port_eff = port.get("eff") or {}
    rows = []
    for p in positions:
        n = set(x for x in (nat[p]["targets"] or []) if x is not None)
        q = set(t for t, s in port_eff.items() if p in s)
        rk = set(t for t, s in port_rk.items() if p in s)
        c = set(t for t, v in cft.items() if p in set(v["moveTiles"])
                or (p == origin and v.get("currentValid")))
        rows.append({"pos": list(p), "natif": sorted(n), "port": sorted(q), "ranked": sorted(rk),
                     "castFromTiles": sorted(c),
                     "diff_port_only": sorted(q - n), "diff_natif_only": sorted(n - q),
                     "bucketUtil": nat[p]["bucketUtil"]})
    n_div = sum(1 for x in rows if x["diff_port_only"] or x["diff_natif_only"])
    # E2 = la TRONCATURE du PLAN : `ranked` perd-il des positions que `castFromTiles` a ?
    #      (diagnostic du HARNAIS -- il reste > 0 apres le fix, et c'est normal : le fix ne
    #      DETRONQUE pas `attackPlans`, il cesse de s'en servir comme gate.)
    e2 = sum(1 for x in rows if set(x["castFromTiles"]) - set(x["ranked"]))
    # E1 se DECOMPOSE, et les confondre fait accuser le gate a tort (mesure sur `1153` :
    #   `cft_only` = le predicat ACCEPTE une cible que le natif n'a pas evaluee -> le port serait
    #                PERMISSIF. C'est le seul sens qui accuse vraiment le gate.
    #   `nat_only` = le natif construit un event pour une entite que le ciblage REFUSE. Sur une
    #                ability AoE c'est la reponse JUSTE : `HammerOfWrathPlaybook` score
    #                `Sigma CalculateUtilityFromDamageEvent` sur la cible ET ses ADJACENTS, donc
    #                l'oracle (ancre sur `ProbableDamageEvent$$.ctor`) capture les eclaboussures.
    #                Mesure : 1153 rend `nat_only = 1` a l'origine (`abilityReason(77)` =
    #                `TargetIsNotAdjacent`, et 77 est pourtant capture). Ce n'est PAS un ecart de
    #                gate -- c'est la meme lecon que `damage_predictions` (#362) : la CAPTURE n'est
    #                pas l'ensemble des cibles ELIGIBLES.
    # => l'egalite ensembliste natif == port n'est concluante que sur une ability MONO-CIBLE
    #    (`1202` : `nat_only = cft_only = 0` aux 33 positions). Ailleurs, seul l'ARGMAX conclut.
    e1_cft_only = sum(1 for x in rows if set(x["castFromTiles"]) - set(x["natif"]))
    e1_nat_only = sum(1 for x in rows if set(x["natif"]) - set(x["castFromTiles"]))
    e1 = sum(1 for x in rows if set(x["castFromTiles"]) != set(x["natif"]))
    cands = (port.get("cands") or [])
    port_arg = ({"pos": list(cands[0]["to"] or origin), "util": cands[0]["pred"],
                 "targets": [cands[0]["target"]]} if cands
                else {"pos": None, "util": None, "targets": []})
    same_pos = (nat_arg["pos"] == port_arg["pos"])
    same_tgt = (bool(port_arg["targets"]) and port_arg["targets"][0] in (nat_arg["targets"] or []))
    separates = not (same_pos and same_tgt)
    if verbose and separates:
        print("    [maxRank=%d] SEPARE : natif %s (u=%s) vs port %s (u=%s)"
              % (mr, nat_arg["pos"], nat_arg["util"], port_arg["pos"], port_arg["util"]))
    return {"maxRank": mr, "rows": rows, "divergentPositions": n_div,
            "e1_predicat": e1, "e1_cft_only": e1_cft_only, "e1_nat_only": e1_nat_only,
            "e2_troncature": e2, "argmaxPort": port_arg,
            "separates": separates, "portGated": port.get("gated"),
            "rankedSizes": str({t: len(s) for t, s in sorted(port_rk.items())}),
            "portRanked": {str(t): sorted(s) for t, s in port_rk.items()}}


def run(fixture: str, max_rank: int | None, ranks: tuple | None = None,
        rings: tuple | None = None, verbose: bool = True) -> dict:
    _resolve_session, _rpc = _rpc_mod()
    sid = _resolve_session()
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    fx = dict(_FIXTURES[fixture])
    if max_rank:
        fx["max_rank"] = int(max_rank)
    if ranks:
        fx["ranks"] = tuple(sorted(set(ranks), reverse=True))
    if rings:
        fx["rings"] = dict(zip(("necroWarden", "ultraTitus"), rings))
        fx["name"] = "%s_r%s" % (fx["name"], "-".join(str(x) for x in rings))
        fx["seed"] = int(fx["seed"]) + sum(rings) * 7
    print("[350-r3a-r3] session %s -- fixture %s (rangs %s, anneaux %s)"
          % (sid, fx["name"], list(fx.get("ranks") or (fx["max_rank"],)), fx["rings"]))
    return {"step1": step1(_rpc, sid, logs, fx, verbose)}


def sweep(dists: tuple, ranks: tuple, near: int, verbose: bool = True) -> dict:
    """Balaye les geometries : pour chaque distance de l'ennemi de plus haute utilite et chaque
    `maxRank`, mesure si les ARGMAX divergent. C'est la recherche EXPLICITE du montage separateur --
    pas une esperance. `near` = anneau du concurrent (le mettre LOIN l'ecarte du bucket)."""
    _resolve_session, _rpc = _rpc_mod()
    sid = _resolve_session()
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    rows = []
    for d in dists:
        for mr in ranks:
            fx = dict(_FIXTURES["carte"])
            fx["name"] = "sweep_d%d_n%d_r%d" % (d, near, mr)
            fx["seed"] = 35100 + d * 100 + near * 10 + mr
            fx["rings"] = {"necroWarden": near, "ultraTitus": d}
            fx["max_rank"] = mr
            print("\n[sweep] ultraTitus a distance %d, necroWarden a %d, maxRank=%d"
                  % (d, near, mr))
            try:
                r = step1(_rpc, sid, logs, fx, verbose)
            except Exception as e:                                   # noqa: BLE001
                r = {"ok": False, "error": str(e)[:200]}
            rows.append({"dist": d, "near": near, "maxRank": mr, "ok": r.get("ok"),
                         "divergent": r.get("divergentPositions"),
                         "e1": r.get("e1_predicat"), "e2": r.get("e2_troncature"),
                         "separates": r.get("separates"),
                         "argmaxNative": r.get("argmaxNative"),
                         "argmaxPort": r.get("argmaxPort"),
                         "error": r.get("error")})
    print("\n[sweep] RESUME")
    for x in rows:
        print("  d=%d near=%d maxRank=%-3d ok=%-5s setsDiv=%-4s E1=%-4s E2=%-4s SEPARE=%s"
              % (x["dist"], x["near"], x["maxRank"], x["ok"], x["divergent"], x["e1"], x["e2"],
                 x["separates"]))
        if x["separates"]:
            print("      natif=%s" % x["argmaxNative"])
            print("      port =%s" % x["argmaxPort"])
    return {"sweep": rows}


def _ints(s: str) -> tuple:
    return tuple(int(x) for x in s.split(",") if x.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture", choices=tuple(_FIXTURES), default="carte")
    ap.add_argument("--max-rank", type=int, default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--dists", default="2,3,4", help="anneaux de l'ennemi de haute utilite")
    ap.add_argument("--ranks", default=None,
                    help="valeurs de maxRank a balayer (defaut : 32,8,6,4,3,2 hors --sweep ; 8 en "
                         "--sweep). 8 = `rl_duel._decision`, 6 = defaut du RPC `decisionView`.")
    ap.add_argument("--near", type=int, default=1, help="anneau du concurrent")
    ap.add_argument("--rings", default=None,
                    help="anneaux des deux ennemis, ex. '1,2' -- PILOTE la geometrie sans creer une "
                         "fixture de plus (le regime de troncature exige plus de tuiles valides "
                         "que `maxRank` : sans ca la mesure est NON DISCRIMINANTE, pas verte)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = (sweep(_ints(a.dists), _ints(a.ranks or "8"), a.near, verbose=not a.json) if a.sweep
           else run(a.fixture, a.max_rank,
                    _ints(a.ranks) if a.ranks else (32, 8, 6, 4, 3, 2),
                    _ints(a.rings) if a.rings else None, verbose=not a.json))
    if a.json:
        print(json.dumps(res, indent=2, default=str))
    s1 = res.get("step1")
    if s1 is not None and not s1.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
