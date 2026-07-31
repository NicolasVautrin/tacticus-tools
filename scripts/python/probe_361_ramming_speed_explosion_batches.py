"""probe #361 (#353-r1 volet b) -- les batchs 3/4 (EXPLOSION) de `RammingSpeed` (1059), CONFRONTES.

OU EN EST LA QUESTION
---------------------
`probe_372_will_be_kill_gate.py` a mesure, capteur #372 vivant : sur l'event du CASTER,
`cannotBeGuaranteedKilled = 0`, `blockScenarioCount = 0`, `willBeKill = TRUE` -- donc
**le predicat de la gate `Any(selfPreds, p => p.WillBeKill)` est VRAI**, et pourtant le natif rend
2 events. Ce n'est donc PAS la gate qui supprime les batchs 3/4.

CE QUE CE PROBE TESTE
---------------------
La seule cause restante : les selecteurs des batchs 3/4 rendent un ensemble VIDE. Lus VERBATIM sur
`IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` :

    tile = RammingSpeedAbility$$GetTileToMoveTo(ability)
    b3   = Friends(<Caster>, AdjacentUnits(tile, 1, 3), 3)
    b4   = Enemies(<Caster>, AdjacentUnits(tile, 1, 3), 3)
    list.AddRange(GenerateAttackPredictions(..., b3, Get(amount), null, Nullable(0xf), 0))
    list.AddRange(GenerateAttackPredictions(..., b4, Get(amount), null, Nullable(0xf), 0))

et `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(origin, unique, selectionType)` COMPOSE
(elle n'alloue aucun selecteur dedie) :

    Units( AdjacentTiles(origin), unique, selectionType )  op_Subtraction  origin

`IdunBattle.AI.Playbook.ComparablePlaybook<T>$$GenerateAttackPredictions` emet **UN event PAR
ENTITE** rendue par le selecteur (boucle sur l'enumerateur de `selector.Select(ctx)`), donc :

    n_events attendu = 1 (batch CIBLE) + 1 (batch CASTER) + |friends(adj(tile))| + |enemies(adj(tile))|

DEUX MESURES SUR LE MEME ETAT, et c'est leur CONJONCTION qui porte le verdict
-----------------------------------------------------------------------------
  1. `fresh` : geometrie DRIVEE pas-a-pas puis `endturn` -- le caster n'a PAS bouge ce tour,
     exactement le montage de `probe_353r1` (celui ou le natif a CONFIRME la tuile 2/2). Le
     voisinage de la tuile d'arrivee porte un AMI et au moins un ENNEMI, par construction VERIFIEE.
  2. `cast` : un CAST REEL de 1059 sur la meme cible, depuis le meme etat. C'est la CONTRE-EPREUVE
     du « pool de tuiles vide », et elle vaut pour la face PREDICTION -- lecture faite :

       `RammingSpeedAbility$$GetDynamicInvalidTargetReason` evalue le MEME arbre
       (`SelectTile(GetTileToMoveTo())`) dans un contexte qu'il construit lui-meme,
       `memset(ctx, 0, 0x128)` puis SEULEMENT `ctx+0x08 = caster`, `ctx+0x10 = target`,
       `ctx+0x40 = casterTiles[0]` -- et rend `0x8000000` (cast REFUSE) des que l'arbre ne rend
       rien. Or `ComparablePlaybook<T>$$GenerateAttackPredictions` construit un contexte qui
       renseigne CES MEMES TROIS champs (`+0x08 = caster`, `+0x10 = target`,
       `+0x40 = UnitPosition$$get_MainTile(casterPosition)`) **et davantage**.

     => un cast qui PASSE prouve que l'arbre rend une tuile dans un contexte STRICTEMENT PLUS
     PAUVRE que celui du playbook. Le pool ne peut donc pas y etre vide.

TROISIEME CONDITION DE MONTAGE, longtemps MANQUANTE (#381) -- le caster doit AVOIR LA MAIN
-------------------------------------------------------------------------------------------
Les deux selecteurs partent de `MovableTilesInRange(Caster@0x48, CasterTile@0x50, Direct(range),
0, 0)`, donc de `IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor` avec
`ignoreUnitFlags = 0`. Or `IdunBattle.Core.Services.MovementQuery$$FindAnyOrAllMoveableTiles`
ouvre sur une garde qui rend AUSSITOT -- en laissant VIDE l'`OrderedSet` que l'appelant vient
d'allouer, sans erreur ni exception :

    if ( (UnitFlagsComponent$$Has(unitFlags, 1) && ignoreUnitFlags == 0)
       || !UnitExtensions$$CanMove(unit) )   return;

=> un caster qui n'a pas la main n'a AUCUNE tuile de mouvement, l'arbre `GetTileToMoveTo` rend
vide, et les batchs 3/4 manquent POUR UNE RAISON DE MONTAGE. Et `drive_to` termine sur un
`endturn` : c'est la PARITE des tours consommes qui decide du camp qui joue -- deux montages
posant la MEME geometrie par des chemins de drive differents ne la laissent pas au meme camp.
C'etait TOUTE la difference entre ce probe (2 events) et `montage_361` (5 events) sur la
geometrie de `#386` sec.1. Le probe appelle donc `ensure_turn` apres le drive, et REFUSE de
conclure si la main n'y est pas.

L'ancienne conclusion -- « l'`origin` des deux selecteurs, l'arbre `GetTileToMoveTo()`, rend VIDE
dans le contexte de `ComparablePlaybook<T>$$GenerateAttackPredictions` » -- est donc REFUTEE :
`probe_381_movable_tiles_query_gate.py` mesure le pool a 51/0/51/0 en balayant les tours sur une
geometrie FIGEE, et la requete nue (`aiMovableTiles`, meme surcharge) s'y accorde 4/4. Ce qui
reste vrai de #365 : la composition `AdjacentUnits` est vivante dans ce contexte
(`probe_361_adjacent_units_selector.py`, 3/3 bras exacts).

Le verdict est DERIVE des champs mesures (jamais un texte ecrit d'avance) -- c'est la propriete de
`probe_372` qui a permis de tuer la 3e cause, on la garde.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_361_ramming_speed_explosion_batches.py
    python probe_361_ramming_speed_explosion_batches.py --level 8 --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _resolve_session, _rpc                     # noqa: E402
from probe_353_ramming_speed_prediction import build_grafted_seed_bc    # noqa: E402
from probe_353r1_ramming_speed_charge_tile import (                     # noqa: E402
    ENEMY2, FILLER_P, GRAFT, MOVE_RANGE, VICTIM, _cast, _ids, _pos, _view,
    controlled_by_current_player, drive_to, ensure_turn)

ABILITY = 1059
BOARD = "MC1_67"
# PV du camp JOUEUR. Le 2e batch est un RECUL qui frappe le caster de `nrOfHits_2` coups : il faut
# `hpBefore(caster) <= willKillDmg` pour que la gate ouvre. Le probe ne le SUPPOSE pas -- il relit
# `willBeKill` du capteur #372 sur l'event self et ECHOUE si la gate est restee fermee.
HP_PLAYER = 60


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed_bc: Path, seed: int, level: int, mult: int) -> int:
    """`--crit/--block-*` a 0 : degat deterministe et `BlockScenarios` vide cote caster (le capteur
    #372 le CONFIRME -- `blockScenarioCount` est mesure, pas suppose)."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", BOARD, "--rank", "17",
           "--seed-bc", str(seed_bc),
           "--p-units", "%s,%s" % (GRAFT, FILLER_P),
           "--a-units", "%s,%s" % (VICTIM, ENEMY2),
           "--unit-stat", "%s:ActiveAbilityLevel=%d,AbilityVariablesMultiplierPercentage=%d"
                          % (GRAFT, level, mult),
           "--hp-player", str(HP_PLAYER),
           "--crit", "0,0", "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _view(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dv, ob, snap, board=board), board, dv


def _tile(state, board, caster, target):
    """La tuile d'arrivee, par le port CONFRONTE en #353-r1 volet (a) (2/2 MATCH contre la position
    ou le natif POSE le caster apres un cast reel)."""
    from engine.runner.abilities.orks import ramming_speed_tile_to_move_to
    return ramming_speed_tile_to_move_to(state, caster, target, MOVE_RANGE)


def _neighbourhood(board, dv, tile_pos, caster_id):
    """Les deux ensembles que les batchs 3/4 selectionnent, derives de la COMPOSITION native
    `AdjacentUnits(origin) = Units(AdjacentTiles(origin)) - origin` : les unites VIVANTES posees sur
    une tuile hex-adjacente a `tile_pos`, ventilees par camp RELATIVEMENT au caster.

    `origin` etant une TUILE, la soustraction finale ne retire aucune unite -- mais la tuile
    d'arrivee est elle-meme libre (elle sort de `CanAddUnit`), donc la question ne se pose pas."""
    units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("alive")}
    cteam = (units.get(int(caster_id)) or {}).get("team")
    tid = board.id_at(tile_pos[0], tile_pos[1])
    ring = {board.coord(n) for n in board.neighbours(tid)} if tid is not None else set()
    friends, enemies = [], []
    for uid, u in sorted(units.items()):
        p = u.get("pos") or {}
        if (p.get("col"), p.get("row")) not in ring:
            continue
        (friends if u.get("team") == cteam else enemies).append(
            {"id": uid, "visualId": u.get("visualId"), "pos": [p.get("col"), p.get("row")]})
    return friends, enemies


def _predict(sid, rid, cid, tid):
    # `gateProbe` (#361, `frida/hooks/features/ai-step/playbook-gate-probe.ts`) : arme le capteur
    # de gate LE TEMPS de l'invocation. TRI-ETAT -- `None` tant que le bundle injecte ne le porte
    # pas, jamais un zero qui se lirait « aucun appel ».
    # `tileProbe` (#370, `frida/hooks/features/ai-step/movable-tiles-probe.ts`) : arme, DANS LA
    # MEME invocation, le capteur du maillon interne de `GetTileToMoveTo`. C'est CE montage-ci qui
    # rend 2 events -- `probe_361_movable_tiles_selector` a mesure que la MEME geometrie, montee
    # par `montage_361.build_montage`, en rend 5 -- donc c'est ICI que le capteur a quelque chose
    # a trancher. Meme TRI-ETAT : `None` tant que le bundle injecte ne le porte pas.
    nat = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tid,
                                        "abilityType": ABILITY,
                                        "gateProbe": True, "tileProbe": True}, 150)
    rows = [{"targetId": e.get("targetId"), "hpBefore": e.get("hpBefore"),
             "healthDmgMin": e.get("healthDmgMin"), "healthDmgMax": e.get("healthDmgMax"),
             "appliedHits": e.get("appliedHits"), "willBeKill": e.get("willBeKill"),
             "willKillDmg": e.get("willKillDmg"),
             "willKillDmgEffective": e.get("willKillDmgEffective"),
             "blockScenarioCount": e.get("blockScenarioCount"),
             "cannotBeGuaranteedKilled": e.get("cannotBeGuaranteedKilled")}
            for e in (nat.get("events") or [])]
    return rows, nat


def _gate_verdict(gp) -> tuple:
    """Traduit le capteur #361 en (etiquette, phrase). TRI-ETAT strict :
      `None`          -> capteur ABSENT du bundle (reinject en attente) ;
      `calls is None` -> capteur DEMANDE mais NON ARME (un maillon n'a pas resolu) ;
      `calls == []`   -> arme, et le natif n'a JAMAIS appele `get_WillBeKill` ;
      un `returned`   -> le verdict que le NATIF a rendu, a confronter au champ decode."""
    if gp is None:
        return ("absent", "capteur #361 absent du bundle injecte (reinject en attente)")
    calls = gp.get("calls")
    if calls is None:
        return ("non-arme", "capteur #361 NON ARME : %s" % gp.get("error"))
    if not calls:
        return ("zero-appel",
                "capteur #361 ARME : le natif n'appelle JAMAIS `get_WillBeKill` pendant "
                "`MakeDamagePredictions` => `Enumerable.Any` n'invoque pas le predicat (la liste "
                "qu'il itere est vide COTE NATIF, alors que la liste rendue porte l'event)")
    if any(c.get("returned") for c in calls):
        return ("rend-true",
                "capteur #361 ARME : `get_WillBeKill` a rendu TRUE (%d appel(s)) => la gate OUVRE, "
                "et la cause est en AVAL -- l'evaluation des selecteurs des batchs 3/4" % len(calls))
    return ("rend-false",
            "capteur #361 ARME : `get_WillBeKill` a rendu FALSE sur %d appel(s) alors que le "
            "decodeur #372 lit `willBeKill = true` sur le MEME event => le natif lit un AUTRE "
            "objet que celui qu'on decode (parametre du lambda en regime fully-shared generic)"
            % len(calls))


def _scan_geometry(state, board, ids, max_targets: int = 24):
    """Cherche, en MUTANT l'etat OFFLINE, une geometrie ou le voisinage de la tuile d'arrivee porte
    un AMI **et** un ENNEMI -- et qui soit un POINT FIXE (poser l'ami change le pool candidat, donc
    peut changer la tuile : on recalcule et on n'accepte que si la tuile tient).

    Contraintes lues au decompile / imposees pour que la mesure soit ATTRIBUABLE :
      * caster NON adjacent a la cible : c'est le regime ou `ExecuteBehaviour` deplace vraiment
        (`If(!IsAdjacent(...), MoveUnit(GetTileToMoveTo()))`) et celui que #353-r1 a confronte ;
      * caster NON adjacent a la tuile d'arrivee : sinon il compterait dans `Friends` (il est son
        propre ami, cf. `DamageUtility.<EvaluateAttackInSteps>d__2$$MoveNext`) et l'attendu
        melangerait deux causes.
    Rend (target, enemy2, caster, ally, tile) ou None. Positions restaurees a la sortie."""
    from engine.runner.components import PositionComponent
    pcs = {v: state.get_entity(ids[v]).get_component(PositionComponent)
           for v in (GRAFT, FILLER_P, VICTIM, ENEMY2)}
    keep = {v: (pc.col, pc.row) for v, pc in pcs.items()}
    walk = sorted(board.coord(t) for t in board.by_id if board.walkable(t))
    six = sorted((t for t in board.by_id
                  if board.walkable(t) and len(board.neighbours(t)) == 6
                  and all(board.walkable(n) for n in board.neighbours(t))),
                 key=lambda t: (hexgeo.distance(board.coord(t), keep[VICTIM]), t))
    far = next((p for p in reversed(walk)), None)
    try:
        for tt in six[:max_targets]:
            tp = board.coord(tt)
            ring = [board.coord(n) for n in board.neighbours_native(tt)]
            if len(ring) != 6:
                continue
            pcs[VICTIM].col, pcs[VICTIM].row = tp
            casters = sorted((p for p in walk
                              if p not in ring and p != tp
                              and 2 <= hexgeo.distance(p, tp) <= MOVE_RANGE),
                             key=lambda p: (hexgeo.distance(p, keep[GRAFT]), p))
            for e2 in sorted(ring, key=lambda p: hexgeo.distance(p, keep[ENEMY2])):
                pcs[ENEMY2].col, pcs[ENEMY2].row = e2
                for cp in casters[:10]:
                    pcs[GRAFT].col, pcs[GRAFT].row = cp
                    # 1) l'ami TRES LOIN -> la tuile "nue"
                    pcs[FILLER_P].col, pcs[FILLER_P].row = far
                    t0 = _tile(state, board, ids[GRAFT], ids[VICTIM])
                    if t0 is None or hexgeo.distance(cp, t0) <= 1:
                        continue
                    # 2) l'ami sur un voisin LIBRE de cette tuile
                    t0id = board.id_at(*t0)
                    occupied = {tp, e2, cp, t0}
                    for ap in sorted(board.coord(n) for n in board.neighbours(t0id)):
                        if ap in occupied or not board.walkable(board.id_at(*ap)):
                            continue
                        pcs[FILLER_P].col, pcs[FILLER_P].row = ap
                        # 3) POINT FIXE : la tuile doit tenir une fois l'ami pose
                        t1 = _tile(state, board, ids[GRAFT], ids[VICTIM])
                        if t1 != t0 or hexgeo.distance(cp, t1) <= 1:
                            continue
                        return tp, e2, cp, ap, t1
    finally:
        for v, pc in pcs.items():
            pc.col, pc.row = keep[v]
    return None


def _measure(sid, rid, state, board, dv, ids, tag: str) -> dict:
    """UN point de mesure : tuile du port + voisinage IMPRIME + events natifs + attendu derive."""
    caster, target = ids[GRAFT], ids[VICTIM]
    tile = _tile(state, board, caster, target)
    out: dict = {"tag": tag, "tile": list(tile) if tile else None,
                 "caster_pos": _pos(dv, caster), "target_pos": _pos(dv, target)}
    if tile is None:
        out["friends"], out["enemies"] = [], []
        out["expected_events"] = 2
    else:
        fr, en = _neighbourhood(board, dv, tile, caster)
        out["friends"], out["enemies"] = fr, en
        out["expected_events"] = 2 + len(fr) + len(en)
    rows, nat = _predict(sid, rid, caster, target)
    out["events"] = rows
    out["n_events"] = len(rows)
    out["playbook"] = nat.get("playbookClass")
    out["native_error"] = nat.get("error")
    out["gate_probe"] = nat.get("gateProbe")
    out["gate_kind"], out["gate_phrase"] = _gate_verdict(nat.get("gateProbe"))
    # Import LOCAL : `probe_361_movable_tiles_selector` importe `_gate_verdict` d'ici -- au niveau
    # module, les deux s'importeraient en cycle.
    from probe_361_movable_tiles_selector import _tile_verdict
    out["tile_probe"] = nat.get("tileProbe")
    out["tile_kind"], out["tile_phrase"] = _tile_verdict(nat.get("tileProbe"))
    self_ev = next((r for r in rows if r["targetId"] == caster), None)
    out["self_will_be_kill"] = (self_ev or {}).get("willBeKill")
    out["gate_open"] = (out["self_will_be_kill"] is True)
    out["explosion_events"] = max(0, out["n_events"] - 2)
    # #381 -- CONDITION DE MONTAGE, pas un diagnostic : les deux selecteurs des batchs 3/4 partent
    # de `MovableTilesInRange(Caster, ...)`, et `MovementQuery$$FindAnyOrAllMoveableTiles` rend
    # AUSSITOT -- en laissant l'`OrderedSet` alloue VIDE, sans erreur -- quand
    # `UnitFlagsComponent$$Has(unitFlags, 1)` est vrai et `ignoreUnitFlags == 0` (le litteral que
    # `GetTileToMoveTo` passe). Un caster qui n'a pas la main n'a donc AUCUNE tuile de mouvement,
    # l'arbre rend vide, et les batchs 3/4 sont absents POUR UNE RAISON DE MONTAGE.
    ctrl = controlled_by_current_player(sid, rid)
    out["caster_has_turn"] = (int(caster) in ctrl) if ctrl else None
    return out


def run(seed: int = 36100, level: int = 8, mult: int = 100, verbose: bool = True,
        ensure_caster_turn: bool = True) -> dict:
    """`ensure_caster_turn=False` est la GARDE ADVERSARIALE de #381, pas une option de confort :
    elle rejoue le montage EXACT d'avant le correctif. Le bras doit alors redevenir NON
    DISCRIMINANT (2 events pour 5 attendus, pool a 0). Un correctif dont on ne sait pas montrer
    qu'il change le resultat n'a rien prouve -- et c'est precisement ce montage-la qui a porte
    quatre hypotheses fausses sur le natif."""
    sid = _resolve_session()
    logs = ROOT / "logs"
    sf = logs / ("p361-%s.json" % uuid.uuid4().hex[:8])
    bcf = logs / ("p361-seed-bc-%s.json" % uuid.uuid4().hex[:8])
    out: dict = {"seed": seed, "level": level, "mult": mult, "board": BOARD}
    out["graft"] = build_grafted_seed_bc(bcf)
    rid = None
    try:
        rid = _build(sf, bcf, seed, level, mult)
        out["runner"] = rid
        state, board, dv = _load(sid, rid)
        ids = _ids(dv)
        geo = _scan_geometry(state, board, ids)
        if geo is None:
            out["error"] = ("aucune geometrie ou le voisinage de la tuile d'arrivee porte un AMI "
                            "et un ENNEMI sur %s -- rien n'est joue" % BOARD)
            return out
        tp, e2, cp, ap, tile0 = geo
        out["geometry"] = {"target": list(tp), "enemy2": list(e2), "caster": list(cp),
                           "ally": list(ap), "tile_predite": list(tile0)}
        wanted = {ids[VICTIM]: tp, ids[ENEMY2]: e2, ids[GRAFT]: cp, ids[FILLER_P]: ap}
        if not drive_to(sid, rid, wanted):
            dv = _view(sid, rid)
            out["error"] = "drive KO : voulu %s obtenu %s" % (
                {k: list(v) for k, v in wanted.items()}, {u: _pos(dv, u) for u in wanted})
            return out

        # --- RENDRE LA MAIN AU CASTER avant de mesurer (#381). `drive_to` termine sur un
        # `endturn`, donc la PARITE des tours consommes decide quel camp joue -- et deux montages
        # qui posent la MEME geometrie par des chemins de drive differents ne la laissent pas au
        # meme camp. C'est ce qui separait ce probe (2 events) de `montage_361` (5 events) sur une
        # geometrie IDENTIQUE. Sans la main, l'arbre `GetTileToMoveTo` part d'un
        # `MovableTilesInRange` VIDE et les batchs 3/4 manquent POUR UNE RAISON DE MONTAGE.
        out["ensure_caster_turn"] = bool(ensure_caster_turn)
        out["turn_given"] = (ensure_turn(sid, rid, ids[GRAFT])
                             if ensure_caster_turn else None)

        # --- mesure `fresh` : le caster n'a PAS bouge ce tour (drive_to termine par `endturn`)
        state, board, dv = _load(sid, rid)
        out["fresh"] = _measure(sid, rid, state, board, dv, ids, "fresh")

        # --- CONTRE-EPREUVE `cast` : le cast REEL, dans le MEME etat. Doit venir APRES la mesure
        # (il consomme le tour). Un cast qui PASSE => l'arbre `GetTileToMoveTo` rend une tuile
        # dans un contexte STRICTEMENT PLUS PAUVRE que celui du playbook (cf. en-tete).
        # `_cast` (foyer unique, probe_353r1) retente en rendant la main : apres le drive c'est le
        # tour d'en face, et un `applyAction ability` hors tour est refuse SANS message.
        act0, after = _cast(sid, rid, ids[GRAFT], ids[VICTIM])
        out["cast"] = {"error": act0.get("error"), "mutated": bool(act0.get("mutated")),
                       "landed": list(after) if after else None,
                       "tile_predite": list(tile0),
                       "match": (tuple(after) == tuple(tile0)) if after else False}
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sf.unlink(missing_ok=True)
        bcf.unlink(missing_ok=True)

    f = out.get("fresh") or {}
    c = out.get("cast") or {}
    # --- VERDICT DERIVE DES CHAMPS (jamais un recit ecrit d'avance)
    if out.get("error"):
        out["ok"] = False
        out["verdict"] = "MONTAGE KO : %s" % out["error"]
    elif f.get("caster_has_turn") is not True:
        # ⚠ CETTE GARDE MANQUAIT, et son absence a coute quatre hypotheses. Sans la main, les deux
        # selecteurs des batchs 3/4 partent d'un pool VIDE que le natif rend correctement (garde
        # d'entree de `MovementQuery$$FindAnyOrAllMoveableTiles`) : le bras mesure alors le
        # montage, pas l'arbre. Le verdict « BATCHS 3/4 ABSENTS SUR UN VOISINAGE PROUVE PEUPLE »
        # accusait le NATIF sur exactement cet etat -- il ne doit plus etre atteignable.
        out["ok"] = False
        out["verdict"] = (
            "BRAS NON DISCRIMINANT : le caster n'a pas la main (caster_has_turn=%s, "
            "ensure_turn=%s). `MovableTilesInRange(Caster, ...)` interroge "
            "`MovementQuery$$GetMovableTilesFor` avec `ignoreUnitFlags = 0`, et "
            "`MovementQuery$$FindAnyOrAllMoveableTiles` rend AUSSITOT -- `OrderedSet` VIDE, sans "
            "erreur -- quand `UnitFlagsComponent$$Has(unitFlags, 1)` est vrai. Les batchs 3/4 "
            "seraient absents POUR UNE RAISON DE MONTAGE, et rien ne serait conclu du natif "
            "(mesure #381 : le pool oscille 51/0/51/0 avec le tour, geometrie figee)."
            % (f.get("caster_has_turn"), out.get("turn_given")))
    elif not f.get("gate_open"):
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : la gate n'est pas ouverte (willBeKill=%s sur "
                          "l'event du caster). Baisser --hp-player." % f.get("self_will_be_kill"))
    elif f.get("expected_events", 0) <= 2:
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : le voisinage de la tuile d'arrivee est VIDE "
                          "(friends=%d enemies=%d) -- la geometrie ne teste rien."
                          % (len(f.get("friends") or []), len(f.get("enemies") or [])))
    elif f.get("n_events") == f.get("expected_events"):
        out["ok"] = True
        out["verdict"] = ("BATCHS 3/4 EMIS ET EXACTS : %d events == attendu (2 + %d amis + %d "
                          "ennemis adjacents a %s). Le verrou de #353-r1 etait un ARTEFACT DE "
                          "MONTAGE."
                          % (f["n_events"], len(f["friends"]), len(f["enemies"]), f["tile"]))
    elif f.get("explosion_events", 0) > 0:
        out["ok"] = False
        out["verdict"] = ("BATCHS 3/4 EMIS mais le COMPTE DIFFERE : %d events pour %d attendus "
                          "(amis=%s ennemis=%s adjacents a %s). C'est un ecart de SELECTEUR, a "
                          "decomposer -- pas un verrou."
                          % (f["n_events"], f["expected_events"],
                             [x["visualId"] for x in f["friends"]],
                             [x["visualId"] for x in f["enemies"]], f["tile"]))
    elif not c.get("mutated"):
        out["ok"] = False
        out["verdict"] = ("BATCHS 3/4 ABSENTS, mais la CONTRE-EPREUVE n'a pas tourne : le cast reel "
                          "a ete REFUSE (%s). Sans lui, « pool de tuiles vide » n'est pas ecarte "
                          "-- le montage est a reprendre, pas la RE." % c.get("error"))
    elif not c.get("match"):
        out["ok"] = False
        out["verdict"] = ("BATCHS 3/4 ABSENTS et la tuile du PORT n'est pas celle du NATIF "
                          "(port=%s, le natif pose le caster en %s). L'ecart est d'abord sur "
                          "`GetTileToMoveTo` -- a traiter avant tout verdict sur les batchs."
                          % (c.get("tile_predite"), c.get("landed")))
    else:
        out["ok"] = False
        out["verdict"] = (
            "BATCHS 3/4 ABSENTS ALORS QUE LES DEUX CONDITIONS DE MONTAGE SONT TENUES : tuile=%s "
            "amis=%s ennemis=%s, gate OUVERTE (willBeKill=True sur l'event du caster), caster AYANT "
            "LA MAIN, et le natif rend %d events. Le cast reel PASSE et pose le caster en %s == la "
            "tuile du port. Les deux causes connues sont donc ECARTEES et il en reste une "
            "INCONNUE : le capteur #370 dit [%s] -- %s. RIEN n'est conclu de l'arbre tant que ce "
            "maillon n'est pas nomme (l'ancienne conclusion « `GetTileToMoveTo` rend VIDE dans le "
            "contexte du playbook » est REFUTEE : cf. #381, le pool oscille 51/0/51/0 avec le "
            "TOUR, geometrie figee). Capteur gate : %s."
            % (f["tile"], [x["visualId"] for x in f["friends"]],
               [x["visualId"] for x in f["enemies"]], f["n_events"], c.get("landed"),
               f.get("tile_kind"), f.get("tile_phrase"), f.get("gate_phrase")))

    if verbose:
        print("[361] runner=%s board=%s niveau=%s | geo=%s"
              % (out.get("runner"), BOARD, level, json.dumps(out.get("geometry"))))
        a = out.get("fresh") or {}
        print("[361] mesure fresh  tuile=%s caster=%s amis=%s ennemis=%s"
              % (a.get("tile"), a.get("caster_pos"),
                 [x["visualId"] for x in (a.get("friends") or [])],
                 [x["visualId"] for x in (a.get("enemies") or [])]))
        print("        events natifs=%s attendu=%s gate_ouverte=%s caster_a_la_main=%s "
              "playbook=%s erreur=%s"
              % (a.get("n_events"), a.get("expected_events"), a.get("gate_open"),
                 a.get("caster_has_turn"), a.get("playbook"), a.get("native_error")))
        for r in a.get("events") or []:
            print("        %s" % json.dumps(r, sort_keys=True))
        print("        capteur gate [%s] : %s" % (a.get("gate_kind"), a.get("gate_phrase")))
        print("        capteur tuile [%s] : %s" % (a.get("tile_kind"), a.get("tile_phrase")))
        print("[361] contre-epreuve cast : mutated=%s erreur=%s tuile_port=%s natif_atterrit=%s "
              "-> %s" % (c.get("mutated"), c.get("error"), c.get("tile_predite"), c.get("landed"),
                         "MATCH" if c.get("match") else "MISMATCH"))
        print("[361] %s" % out.get("verdict"))
        print("[361] -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=36100)
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--mult", type=int, default=100)
    ap.add_argument("--no-ensure-turn", action="store_true",
                    help="GARDE ADVERSARIALE (#381) : rejoue le montage d'AVANT le correctif "
                         "(pas d'`ensure_turn` apres le drive). Le bras doit redevenir NON "
                         "DISCRIMINANT -- s'il reste vert, le correctif ne discrimine rien")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, level=a.level, mult=a.mult, verbose=not a.json,
              ensure_caster_turn=not a.no_ensure_turn)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
