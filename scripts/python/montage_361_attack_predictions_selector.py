"""Montage NOMME : confronter le SELECTEUR d'un batch `GenerateAttackPredictions` au natif (#365).

POURQUOI CE MONTAGE EXISTE
--------------------------
`IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` rend 2 events la ou ses
batchs 3/4 en attendraient 5, gate OUVERTE (capteur #361 : `get_WillBeKill -> TRUE`). Les deux
`ComparablePlaybook<T>$$GenerateAttackPredictions` rendent donc VIDE. Leurs selecteurs sont

    Friends(Caster@0x48, AdjacentUnits(RammingSpeedAbility$$GetTileToMoveTo(), 1, 3), 3)
    Enemies(Caster@0x48, AdjacentUnits(RammingSpeedAbility$$GetTileToMoveTo(), 1, 3), 3)

et `IdunBattleLogic.Entities.DSLSelectors$$Friends` / `$$Enemies` allouent le MEME
`UnitsFromFactionSelector` a un seul bit pres (`friends = 1` / `friends = 0`, lu au decompile).
Leur `Select` evalue `entities` UNE fois puis PARTITIONNE par `UnitExtensions$$HasFaction`. Donc

    Friends(X) et Enemies(X) TOUS DEUX vides  <=>  X vide.

`X = AdjacentUnits(origin, 1, 3)` se decompose, VERBATIM (`DSLSelectors$$AdjacentUnits` n'alloue
aucun selecteur dedie) :

    Units( AdjacentTiles(origin), unique=1, selectionType=3 )  op_Subtraction  origin

`ComparablePlaybook<T>$$GenerateAttackPredictions` appelle sur le selecteur RACINE
`TargetsSelector$$SelectUniqueUnits(ctx, 3)`, dans un contexte qu'il construit lui-meme.

CE QUE LE MONTAGE ISOLE
-----------------------
Trois playbooks seulement appellent `GenerateAttackPredictions` (xrefs) :
`ExplosivePresentsPlaybook`, `MortisRoundPlaybook`, `RammingSpeedPlaybook` (x2). Les deux premiers
sont donc les seuls temoins possibles, et ils encadrent EXACTEMENT la question :

  * `MortisRoundPlaybook$$MakeDamagePredictions`     -> selecteur `Entity(target)`
    = le chemin `GenerateAttackPredictions` NU, sans aucune composition. Controle POSITIF.
  * `ExplosivePresentsPlaybook$$MakeDamagePredictions` -> selecteur
    `ExplosivePresentsAbility$$GetTargets()` = `(Target@0x60 + AdjacentUnits(Target@0x60, 1, 3))
    op_Subtraction Caster@0x48`
    = la MEME `AdjacentUnits(..., 1, 3)`, la MEME `op_Subtraction`, la MEME
    `SelectUniqueUnits(ctx, 3)` -- et un `origin` SIMPLE (`Target`) au lieu de l'arbre
    `GetTileToMoveTo()`. C'est le seul terme qui differe de `RammingSpeed`.

=> le montage rend la question BINAIRE : `AdjacentUnits` vit-elle dans le contexte que
`GenerateAttackPredictions` construit, oui ou non.

CONFRONTABILITE
---------------
`ExplosivePresents` (1170) n'a qu'un porteur `npc` (`orksRedGobbo`) ; `MortisRound` (1004) n'a que
des `npc` et un `lineup`. Les deux playbooks ne lisent NI stats NI traits du caster (leur montant
vient de la config d'ability, leur ciblage d'un arbre pur) -> greffe legitime (`case-92` sec.5bis).
On greffe les DEUX sur le MEME porteur du pool que #353 a etabli (`orksKillaKan`), avec la MEME
geometrie et la MEME seed : entre les deux bras, SEULE l'ability change.

ASCII only (cp1252).
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _rpc                                        # noqa: E402
from probe_353_ramming_speed_prediction import build_grafted_seed_bc     # noqa: E402
from probe_353r1_ramming_speed_charge_tile import (                      # noqa: E402
    ENEMY2, FILLER_P, GRAFT, VICTIM, _ids, _pos, _view, drive_to)

BOARD = "MC1_67"
RANK = "17"


@dataclass
class SelectorArm:
    """Un bras = UNE ability dont le playbook passe par `GenerateAttackPredictions`."""
    key: str
    ability: int
    ability_name: str
    playbook: str            # `playbookClass` attendu du RPC -- verifie, jamais suppose
    selector: str            # le selecteur natif, VERBATIM
    kind: str                # "entity" (controle positif) | "adjacent" (discriminant)


ARMS = {
    "control": SelectorArm(
        key="control", ability=1004, ability_name="MortisRound",
        playbook="MortisRoundPlaybook",
        selector="Entity(target)",
        kind="entity"),
    "adjacent": SelectorArm(
        key="adjacent", ability=1170, ability_name="ExplosivePresents",
        playbook="ExplosivePresentsPlaybook",
        selector="(Target@0x60 + AdjacentUnits(Target@0x60, 1, 3)) - Caster@0x48",
        kind="adjacent"),
}


@dataclass
class Montage:
    runner: int
    state: object
    board: object
    dv: dict
    ids: dict
    geometry: dict
    graft: dict
    state_file: Path
    seed_bc: Path
    errors: list = field(default_factory=list)


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed_bc: Path, seed: int, level: int) -> int:
    """`--crit/--block-*` a 0 et PV genereux : on compte des EVENTS, pas des degats -- aucun
    aleatoire ne doit pouvoir tuer une unite entre le drive et la mesure."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", BOARD, "--rank", RANK,
           "--seed-bc", str(seed_bc),
           "--p-units", "%s,%s" % (GRAFT, FILLER_P),
           "--a-units", "%s,%s" % (VICTIM, ENEMY2),
           "--unit-stat", "%s:ActiveAbilityLevel=%d" % (GRAFT, level),
           "--crit", "0,0", "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1400:]))
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


def scan_geometry(board, dv, caster_adjacent: bool = False, max_targets: int = 40):
    """Cherche une geometrie ou le VOISINAGE DE LA CIBLE est peuple -- c'est ce que
    `AdjacentUnits(Target, 1, 3)` selectionne, donc c'est la seule chose que la geometrie doit
    garantir. On DEPLACE les unites pour l'obtenir (jamais « bloque par le spawn »).

    `caster_adjacent=False` : caster a distance >= 2 de la cible. Attendu = cible + 2 voisins.
    `caster_adjacent=True`  : caster POSE sur un 3e voisin de la cible. Le natif le RETIRE
        (`op_Subtraction Caster@0x48`), donc l'attendu ne bouge PAS -- c'est le bras qui
        DISCRIMINE la soustraction (un port qui l'oublierait rendrait un event de plus).

    Rend un dict {target, ally, enemy2, caster} de positions, ou None.
    """
    walk = sorted(board.coord(t) for t in board.by_id if board.walkable(t))
    six = [t for t in board.by_id
           if board.walkable(t) and len(board.neighbours(t)) == 6
           and all(board.walkable(n) for n in board.neighbours(t))]
    for tt in sorted(six)[:max_targets]:
        tp = board.coord(tt)
        ring = sorted(board.coord(n) for n in board.neighbours(tt))
        if len(ring) < 3:
            continue
        ally, enemy2 = ring[0], ring[1]
        if caster_adjacent:
            caster = ring[2]
        else:
            caster = next((p for p in walk
                           if p != tp and p not in ring and hexgeo.distance(p, tp) >= 2), None)
        if caster is None:
            continue
        return {"target": tp, "ally": ally, "enemy2": enemy2, "caster": caster}
    return None


def build_montage(sid, arm: SelectorArm, seed: int, level: int = 8,
                  caster_adjacent: bool = False) -> Montage:
    """Monte un runner ou `arm.ability` est GREFFEE sur `GRAFT`, puis DRIVE la geometrie.

    L'appelant est responsable de disposer le runner (`dispose_montage`)."""
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    sf = logs / ("m361-%s-%s.json" % (arm.key, tag))
    bcf = logs / ("m361-seed-bc-%s-%s.json" % (arm.key, tag))
    graft = build_grafted_seed_bc(bcf, graft=GRAFT, ability_id=arm.ability,
                                  ability_name=arm.ability_name)
    rid = _build(sf, bcf, seed, level)
    state, board, dv = _load(sid, rid)
    ids = _ids(dv)
    errors = []
    geo = scan_geometry(board, dv, caster_adjacent=caster_adjacent)
    if geo is None:
        errors.append("aucune geometrie a 6 voisins marchables sur %s" % BOARD)
    else:
        wanted = {ids[VICTIM]: geo["target"], ids[FILLER_P]: geo["ally"],
                  ids[ENEMY2]: geo["enemy2"], ids[GRAFT]: geo["caster"]}
        if not drive_to(sid, rid, wanted):
            dv = _view(sid, rid)
            errors.append("drive KO : voulu %s obtenu %s"
                          % ({k: list(v) for k, v in wanted.items()},
                             {u: _pos(dv, u) for u in wanted}))
        state, board, dv = _load(sid, rid)
    return Montage(runner=rid, state=state, board=board, dv=dv, ids=ids,
                   geometry=geo or {}, graft=graft, state_file=sf, seed_bc=bcf, errors=errors)


def dispose_montage(sid, m: Montage) -> None:
    if m is None:
        return
    if m.runner is not None:
        _r(sid, "disposeRunner", {"runnerId": m.runner}, 30)
    m.state_file.unlink(missing_ok=True)
    m.seed_bc.unlink(missing_ok=True)


def expected_targets(arm: SelectorArm, board, dv, caster_id: int, target_id: int) -> dict:
    """Derive l'ensemble ATTENDU du selecteur NATIF (jamais un nombre ecrit d'avance).

    `entity`   -> {target}.
    `adjacent` -> {target} UNION {unites VIVANTES sur une tuile adjacente a target} MOINS {caster}.
                  `MatchesUnitSelectionType(u, 3)` = vivante ET sans le flag 0x11 ; aucune unite du
                  montage ne le porte, donc le filtre se reduit a « vivante ».
    """
    units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("alive")}
    if arm.kind == "entity":
        picked = [int(target_id)]
    else:
        tp = _pos(dv, target_id)
        tid = board.id_at(tp[0], tp[1]) if tp else None
        ring = {board.coord(n) for n in board.neighbours(tid)} if tid is not None else set()
        picked = [int(target_id)]
        for uid, u in sorted(units.items()):
            if uid == int(target_id) or uid == int(caster_id):
                continue
            p = u.get("pos") or {}
            if (p.get("col"), p.get("row")) in ring:
                picked.append(uid)
    return {"ids": picked, "n": len(picked),
            "detail": [{"id": i, "visualId": (units.get(i) or {}).get("visualId"),
                        "pos": list(_pos(dv, i) or [])} for i in picked]}
