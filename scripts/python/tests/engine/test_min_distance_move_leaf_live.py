"""GARDE de la feuille de MOUVEMENT `MinDistanceToClosestEnemy(16)` — confrontee au NATIF.

Ce que cette garde verrouille (residu #17 / case-52 §#57k-#57l, ferme le 2026-07-28) :

1. **Le TERME, pas l'issue du pas.** Pour CHAQUE tuile du movable set d'un pas de move PUR,
   `MinDistanceToClosestEnemyUtility.get_min_distance_to_enemy` (port) doit rendre la valeur
   NATIVE : `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy`
   = `MIN` sur le footprint du **ClosestEnemy FIGE** de `IPathfinders.GetPath(type=1, unit,
   tuile, tuileEnnemie, null).Count` (le `Count` est un nombre de NOEUDS, extremites incluses).
   L'oracle est le RPC `pathDistToEnemies`, qui invoque ce meme pathfinder natif et mirrore
   les filtres de `IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext`
   (`!CurrentOwnerIsEnvironment` / `IsTargetable` / `!IsIrrelevantObject` / vivant / `GetOnlyTargets`).
   Un ecart d'UN SEUL pas sur ce terme suffit a faire choisir une autre tuile : c'etait
   exactement le residu s5 seed 12345 (natif -700 sur (0,4) ET (1,4), port -600 sur (1,4)).

2. **Le DEPARTAGE du tie.** Quand deux tuiles sont a EGALITE d'utilite de mouvement, le natif
   ne tire pas au sort : `MovementActionGenerator.<GenerateActions>d__6$$MoveNext` balaie les
   tuiles dans l'ordre du movable set et le bucket garde le PREMIER maximum (premier-gagne).
   La tuile choisie par le natif doit donc etre celle de plus petit index parmi les ex-aequo.

Historique du piege : sans le filtre `IsTargetable`, un ennemi en Deep-Strike (non atterri,
donc NON ciblable) ecrasait le ClosestEnemy et raccourcissait la distance d'une tuile sur deux
-- une degradation invisible tant qu'on ne regarde que la tuile finalement choisie.

MORDANT VERIFIE (mutation adversariale du 2026-07-29) : en faisant rendre `pd - 1` a
`get_min_distance_to_enemy` (le bug d'ARETES-vs-NOEUDS de la face offline, tache `#17-off`), le
premier test passe ROUGE sur les DEUX couples (87 tuiles divergentes sur 777/C4_09). Le second
reste VERT sous la meme mutation -- et c'est la preuve, pas un trou : un offset UNIFORME ne
deplace aucun argmax, donc le departage du tie ne peut pas le voir. Les deux tests couvrent des
proprietes differentes ; ne pas en deduire que le second est faible.
"""
from __future__ import annotations

import pytest

import engine_validate as EV
import hexgeo
from engine import weights
from engine.ai import context as _ai_ctx
from engine.ai.state_bridge import _is_untargetable
from engine.entities.pathfinding.board import Board
from engine.entities.pathfinding.walk_pathfinder import get_reachable_levels
from engine.runner.snapshot import load_state
from engine.utilities.move import MIN_DIST_UTILITY
from engine_agreement_stages import StageProbe as _StageProbe


class _MoveLeafProbe:
    """Sonde `run_agreement` : capture, a chaque pas de move PUR, le terme MinDist par tuile
    (port live) face au `pathDist` natif du RPC, plus l'ordre du movable set."""

    def __init__(self, sid, rid, rpc, wt):
        self.sid, self.rid, self.rpc, self.wt = sid, rid, rpc, wt
        self.steps: list = []

    def __call__(self, step, uid, dv, mov_by_unit, nat, eng, predictor):
        if not nat.get("move") or nat.get("ability"):
            return                                   # chunk compose : la position suit l'ability
        pd = self.rpc("pathDistToEnemies", {"runnerId": self.rid, "unitId": uid}, 90)
        if not (isinstance(pd, dict) and pd.get("ok")):
            return
        nat_pd = {(t["col"], t["row"]): t["pathDist"] for t in (pd.get("tiles") or [])}
        ctx = _ai_ctx.build(self.rpc, self.rid, dv, mov_by_unit, uid, self.wt, predictor)
        order = [(t["col"], t["row"]) for t in ctx.move_tiles]
        rows = []
        for t in order:
            dn = nat_pd.get(t)
            if dn is None or dn < 0:
                continue                             # tuile inatteignable : hors oracle
            rows.append((t, dn, MIN_DIST_UTILITY.get_min_distance_to_enemy(
                t, ctx.tgt_epos or ctx.epos, ctx.pathdist_by_pos)))
        # Utilite de MOUVEMENT COMPLETE par tuile (`UnitMovement(6) = Tile(7) + MinDist(16)`) :
        # le tie que le natif departage porte sur la SOMME, pas sur la seule feuille MinDist.
        # Meme foyer de calcul que la sonde d'agreement (aucune reimplementation locale).
        mu = _StageProbe(self.sid, self.rid, self.wt)._move_utils(ctx, order)
        self.steps.append({
            "step": step, "uid": uid, "order": order, "rows": rows,
            "u_by_tile": {t: v["u"] for t, v in mu.items()},
            "nat_to": tuple(nat["move"]["to"]),
            "eng_to": tuple(eng["to"]) if eng.get("to") else None,
            "closest_resolved": bool(pd.get("closestResolved")),
            "enemy_count": pd.get("enemyCount"),
            "wmin": self.wt.sub("MinDistanceToClosestEnemy", "PerTileDistance"),
        })


def _walk(host, live_session, build_runner, seed, board, steps):
    rid = build_runner(seed=seed, board=board)["rid"]
    wt = weights.load()

    def _rpc(method, body=None, timeout=60):
        r = host._rpc(live_session, method, [body] if body is not None else [], timeout=timeout)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r)

    probe = _MoveLeafProbe(live_session, rid, _rpc, wt)
    EV.run_agreement(live_session, rid, steps, wt, log=lambda *a, **k: None, probe=probe)
    return probe


@pytest.mark.parametrize("seed,board,steps", [("12345", "MC1_67", 6), ("777", "C4_09", 6)])
def test_min_distance_leaf_equals_native_pathdist(host, live_session, build_runner,
                                                  seed, board, steps):
    """Le terme MinDist du port == la valeur native, TUILE PAR TUILE (pas seulement la tuile choisie)."""
    probe = _walk(host, live_session, build_runner, seed, board, steps)
    measured = [s for s in probe.steps if s["rows"]]
    assert measured, (
        f"seed={seed} board={board} : aucun pas de move PUR mesure sur {steps} pas -- "
        "la garde n'a RIEN confronte (re-crafter le montage, ne pas lire ce vert)")
    bad = []
    for s in measured:
        for (tile, d_nat, d_port) in s["rows"]:
            if d_port != d_nat:
                bad.append((s["step"], s["uid"], tile, d_nat, d_port))
    assert not bad, (
        f"seed={seed} board={board} : le terme MinDist du port diverge du natif "
        f"(GetPath(...).Count) sur {len(bad)} tuile(s) : "
        + "; ".join(f"step{st} u{u} {t} natif={dn} port={dp}" for (st, u, t, dn, dp) in bad[:8]))
    # Le ClosestEnemy doit avoir ete RESOLU au moins une fois : sinon le RPC serait retombe sur
    # son fallback min-sur-tous et l'oracle ne testerait pas la selection d'ennemi.
    assert any(s["closest_resolved"] for s in measured), \
        f"seed={seed} board={board} : ClosestEnemy jamais resolu -- oracle degrade"


@pytest.mark.parametrize("seed,board,steps", [("12345", "MC1_67", 6)])
def test_move_tie_is_broken_by_movable_set_order(host, live_session, build_runner,
                                                 seed, board, steps):
    """Tie d'utilite de mouvement -> le natif prend la PREMIERE tuile du movable set (premier-gagne).

    Restreint aux pas ou natif ET moteur choisissent la MEME tuile : ailleurs, l'ecart peut venir
    d'une AUTRE feuille du composite (Tile(7) et ses sous-feuilles), pas du departage.
    """
    probe = _walk(host, live_session, build_runner, seed, board, steps)
    checked = 0
    for s in probe.steps:
        if not s["rows"] or s["nat_to"] != s["eng_to"]:
            continue
        by_tile = s["u_by_tile"]                     # Tile(7) + MinDist(16), la SOMME
        nat_to = s["nat_to"]
        if nat_to not in by_tile:
            continue
        umax = max(by_tile.values())
        if by_tile[nat_to] != umax:
            continue                                 # une autre feuille domine : hors sujet ici
        ties = [t for (t, u) in by_tile.items() if u == umax]
        if len(ties) < 2:
            continue
        idx = {t: s["order"].index(t) for t in ties if t in s["order"]}
        assert idx and nat_to in idx, f"tuile native {nat_to} hors du movable set"
        assert idx[nat_to] == min(idx.values()), (
            f"seed={seed} step{s['step']} u{s['uid']} : {len(ties)} tuiles a utilite de mouvement "
            f"egale ({by_tile[nat_to]}), le natif a pris {nat_to} (index {idx[nat_to]}) alors que "
            f"l'index minimum est {min(idx.values())} -- le departage n'est pas premier-gagne")
        checked += 1
    assert checked, (
        f"seed={seed} board={board} : aucun tie MinDist rencontre sur {steps} pas -- "
        "la garde du departage n'a RIEN confronte")


# ---------------------------------------------------------------------------------------------
# Generalisation CRAFTEE : un ennemi DEEP-STRIKE strictement PLUS PROCHE que tout ennemi ciblable.
# C'est le regime exact du residu #57l -- et il n'avait aucune garde cote MinDist : `test_deep_
# strike_live` verrouille la ciblabilite et l'aura, pas la distance de mouvement.
# ---------------------------------------------------------------------------------------------

DS_ENEMIES = "eldarAutarch,necroWarden,necroWarden"   # Autarch = TeleportStrike (deep-strike)


def _drive_tile(rpc, rid, mover_id, anchor, away=False):
    """Tuile legale du mover la plus PROCHE (ou la plus LOIN si `away`) de `anchor`.
    Pilotage pur (`side="enemy"` : on conduit AUSSI le camp adverse) -- aucune mecanique testee ici."""
    mv = rpc("aiMovableTiles", {"runnerId": rid, "side": "enemy"}, 90) or {}
    for row in (mv.get("units") or []):
        if row.get("unitId") != mover_id:
            continue
        tiles = [(t["col"], t["row"]) for t in (row.get("tiles") or [])]
        if not tiles:
            return None
        key = (lambda t: -hexgeo.distance(t, anchor)) if away \
            else (lambda t: hexgeo.distance(t, anchor))
        return min(tiles, key=key)
    return None


def _move(rpc, rid, uid, to):
    rpc("applyAction", {"runnerId": rid,
                        "action": {"kind": "move", "unitId": uid,
                                   "to": {"col": to[0], "row": to[1]}}}, 60)


def test_deep_strike_enemy_excluded_from_min_distance_live(host, live_session, rpc, build_runner):
    """Un ennemi NON CIBLABLE (deep-strike) plus proche ne doit PAS raccourcir le terme MinDist."""
    rid = build_runner(seed="777", board="MC1_67",
                       extra=["--a-units", DS_ENEMIES, "--no-ai"])["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    obs = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym")
    state = load_state(dv, obs, snap, board=board)

    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive") and u.get("pos")]
    foes = [u for u in units if not u.get("ctrl") and u.get("alive") and u.get("pos")]
    ds = [u for u in foes if _is_untargetable(state, u["id"])]
    if not (mine and ds and len(foes) > len(ds)):
        pytest.skip("montage non forme : il faut un ennemi deep-strike ET un ennemi ciblable")
    autarch = ds[0]
    a_pos = (autarch["pos"]["col"], autarch["pos"]["row"])
    me = min(mine, key=lambda u: hexgeo.distance((u["pos"]["col"], u["pos"]["row"]), a_pos))

    # DRIVE : on RECULE les ennemis CIBLABLES loin de mon unite -- sans ce creux, le filtre
    # `IsTargetable` ne serait pas discriminant (les 3 ennemis spawnent groupes).
    #
    # ⚠ On ne DEPLACE PAS le deep-strike : `TeleportStrike` dit « non ciblable jusqu'a ce qu'il ait
    # AGI » -- un `applyAction move` sur lui le fait ATTERRIR et il redevient une cible legitime
    # (mesure du 2026-07-29 : `enemies=[77,79,81]` apres l'avoir bouge). Le creux se fait donc
    # uniquement du cote des ciblables. `applyAction` ne verifie pas la propriete : on pilote les
    # deux camps, mais chaque unite n'a qu'UNE activation par tour.
    my_pos = (me["pos"]["col"], me["pos"]["row"])
    for f in foes:
        if f["id"] == autarch["id"]:
            continue
        far = _drive_tile(rpc, rid, f["id"], my_pos, away=True)
        if far is not None:
            _move(rpc, rid, f["id"], far)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    obs = rpc("observeBattle", {"runnerId": rid}, 60)
    state = load_state(dv, obs, snap, board=board)
    pd = rpc("pathDistToEnemies", {"runnerId": rid, "unitId": me["id"]}, 90)
    assert isinstance(pd, dict) and pd.get("ok"), f"pathDistToEnemies KO: {str(pd)[:200]}"
    kept = {e["id"] for e in (pd.get("enemies") or [])}

    # (1) le deep-strike est EXCLU du ClosestEnemy natif
    assert autarch["id"] not in kept, (
        f"l'ennemi deep-strike u{autarch['id']} est retenu comme cible du ClosestEnemy "
        f"(enemies={sorted(kept)}) -- le filtre IsTargetable ne mord plus")
    assert kept, "aucun ennemi ciblable retenu -- oracle vide"

    # (2) l'exclusion est LIANTE : le chemin vers le deep-strike est STRICTEMENT plus court que la
    #     distance native, sur au moins une tuile. Sinon ce montage ne prouverait rien.
    cur_a = next(u for u in (dv.get("units") or []) if u["id"] == autarch["id"])
    a_tile = board.id_at(cur_a["pos"]["col"], cur_a["pos"]["row"])

    def _free_edge(b, x, y, _occ, _team):
        t = b.by_id.get(y)
        return bool(t and t["walkable"] and abs(b.elevation(y) - b.elevation(x)) <= 1)

    lv = {board.coord(t): d for t, d in
          get_reachable_levels(board, a_tile, {}, None, edge=_free_edge).items()}
    nat_pd = {(t["col"], t["row"]): t["pathDist"] for t in (pd.get("tiles") or [])}
    binding = [t for t, dn in nat_pd.items()
               if dn is not None and dn >= 0 and lv.get(t) is not None and lv[t] + 1 < dn]
    assert binding, (
        "montage NON discriminant : le deep-strike n'est plus proche sur AUCUNE tuile "
        f"(natif={sorted(nat_pd.items())[:4]}) -- re-crafter la geometrie, ne pas lire ce vert")

    # (3) et le port rend EXACTEMENT la meme chose que le natif sur toutes les tuiles
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {r["unitId"]: r for r in (mov.get("units") or [])}
    ctx = _ai_ctx.build(lambda m, b=None, t=60: rpc(m, b, t), rid, dv, mov_by_unit,
                        me["id"], weights.load(), None)
    bad = [(t, dn, MIN_DIST_UTILITY.get_min_distance_to_enemy(
                t, ctx.tgt_epos or ctx.epos, ctx.pathdist_by_pos))
           for t, dn in nat_pd.items() if dn is not None and dn >= 0]
    bad = [(t, dn, dp) for (t, dn, dp) in bad if dp != dn]
    assert not bad, (
        f"deep-strike plus proche sur {len(binding)} tuile(s) : le port diverge du natif sur "
        f"{len(bad)} tuile(s) : {bad[:6]}")
