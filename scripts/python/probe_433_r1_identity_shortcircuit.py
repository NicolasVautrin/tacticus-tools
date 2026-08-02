"""#433-r1 -- le COURT-CIRCUIT D'IDENTITE d'`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`.

RE (decompile = verite). La surcharge SCALAIRE `(tile1, tile2)` lit d'abord les DEUX elevations
(composant a `+0x18` sur chaque entite-tuile ; l'une des deux absente -> elle LEVE), puis :

    dElev = |elev2 - elev1|
    b     = (tile1 == tile2) ? 1 : ConnectivityComponent$$IsNeighbour(tile1.Connectivity, tile2)
    return (dElev < 2) & b

DEUX faits que la paraphrase << distance hex == 1 >> manque, et le present probe les mesure
SEPAREMENT :

  (I) IDENTITE -- le test porte sur l'IDENTITE DE REFERENCE des deux entites-tuile (`tile1 == tile2`
      compare les pointeurs, PAS des coordonnees ni un Id), il court-circuite `IsNeighbour`, et il
      rend VRAI. Le gate d'elevation ne peut pas le contredire : sur une meme entite `dElev = 0 < 2`.
      Une tuile est donc adjacente A ELLE-MEME, INCONDITIONNELLEMENT.
  (E) ELEVATION -- deux voisines separees de 2 crans ou plus ne sont PAS adjacentes.

Les DEUX termes sont foldes DANS LA PRIMITIVE, donc tout consommateur en herite : `TileExtensions$$
IsAdjacentTo` (les deux surcharges) et `IsAdjacentToAll` sont des passe-plats ; la surcharge LISTE
`AreTilesAdjacent(IList, IList)` boucle sur la scalaire ; `BattleQuery$$AreEntitiesAdjacent` (ses
TROIS surcharges) appelle la surcharge LISTE. Un port qui remplace la primitive par `board.neighbours`
nu, ou par `hexgeo.distance == 1`, perd les deux -- silencieusement.

CE QUE LE PROBE MESURE
----------------------
  etape A (OFFLINE) -- la PROPRIETE (I) sur chaque foyer DECLARE du port. La liste est nommee ici :
      un foyer qui pretend porter `AreTilesAdjacent` et rend FAUX sur une paire identique est un
      ecart, quelle que soit l'atteignabilite de son regime.
  etape B (OFFLINE) -- le foyer du residu, `TitanhammerSquad_TeleportingInEffect$$
      GetCustomMovingEffectCondition` (vslot 0x748), sur ses DEUX termes : (I) une destination QUI
      EST une marque autre que la premiere, et (E) une destination voisine d'une marque a
      |dElev| >= 2.
  etape C (OFFLINE) -- le GISEMENT de (E) : combien de boards de `data/boards/**` portent une paire
      de tuiles VOISINES a |dElev| >= 2. C'est ce qui separe << terme theorique >> de << terme qui
      mord >>.
  etape D (LIVE)    -- confrontation port/natif du foyer corrige, sur une destination voisine de la
      marque a |dElev| >= 2. Montage repris de `probe_448_r2d_titanhammer_squad.py` (importe comme
      harnais, jamais recopie) : `astarLysander` injecte au catalogue caste `1231`, le natif pose
      `1571` sur la tuile visee, l'etat du port est RECHARGE du natif, puis UN pas est joue des deux
      cotes. Attendu : AUCUN `1574` des deux cotes -- le port d'AVANT en posait un.

REGIME NON CONFRONTABLE, ET DIT COMME TEL : (I) dans le foyer du vslot 0x748 exige `|marked| > 1`,
or `TitanhammerSquadAbility$$ExecuteBehaviour` ne pose qu'UNE marque (`AddEffect(0x623, ...,
targets: <Sel+0x60> = Target)`) -- l'etape D publie la cardinalite mesuree. A cardinalite 1 le bras
`Contains` couvre deja `dest == marked[0]`, donc (I) y est SANS OBJET : c'est (E) qui discrimine.
L'attestation LIVE de (I) elle-meme passe par un AUTRE consommateur, le filtre statique de ciblage
sous `OnlyAdjacent` (`probe_targeting_masks_lot4.py --groups steeljack`, cible = la propre tuile du
caster), ou elle est deja mesuree.

Usage (depuis scripts/python) :
    python probe_433_r1_identity_shortcircuit.py              # A + B + C + D
    python probe_433_r1_identity_shortcircuit.py --offline    # A + B + C seules (aucun runner)
    python probe_433_r1_identity_shortcircuit.py --mutate     # CONTRE-EPREUVE (doit rougir)

ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                             # noqa: E402
import probe_448_r2d_titanhammer_squad as H               # noqa: E402  (harnais LIVE)

BOARDS = ROOT / "data" / "boards"


# --------------------------------------------------------------------------- un board jouet

COLS, ROWS = 7, 7


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _toy_board(elev_by_pos=None):
    """Un board PLAT (ou a elevation choisie) au meme format que `boardGraph`."""
    from engine.entities.pathfinding.board import Board
    elev_by_pos = elev_by_pos or {}
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row,
                          "elevation": int(elev_by_pos.get((col, row), 0)),
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


# --------------------------------------------------------------------------- etape A

def etape_a(fails: list) -> None:
    """La propriete (I) sur les foyers DECLARES. Chaque entree porte le SYMBOLE natif dont elle est
    le mirror -- c'est ce qui rend la liste verifiable plutot que declarative."""
    from engine.runner.abilities.targeting import (are_entities_adjacent,
                                                   are_tiles_adjacent as tgt_adj)
    from engine.services.battle_query import are_tiles_adjacent as bq_adj

    board = _toy_board()
    p = (3, 3)
    tid = board.id_at(p[0], p[1])
    cases = [
        ("runner/abilities/targeting.py::are_tiles_adjacent",
         "IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent (scalaire)",
         lambda: tgt_adj(board, tid, tid)),
        ("runner/abilities/targeting.py::are_entities_adjacent",
         "IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent -> surcharge LISTE",
         lambda: are_entities_adjacent(board, [p], [p])),
        ("services/battle_query.py::are_tiles_adjacent (AVEC board)",
         "IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent / $$AreUnitsInMelee",
         lambda: bq_adj(p, p, board)),
        ("services/battle_query.py::are_tiles_adjacent (SANS board)",
         "IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent (degradation hex pure)",
         lambda: bq_adj(p, p, None)),
    ]
    print("=== etape A -- (I) identite : chaque foyer declare doit rendre VRAI sur (t, t) ===")
    for name, sym, fn in cases:
        got = fn()
        print("  %-52s -> %r   [%s]" % (name, got, sym))
        if got is not True:
            fails.append("A : %s rend %r sur une paire IDENTIQUE (le natif rend VRAI par "
                         "court-circuit, et |dElev| = 0 < 2 ne peut pas le contredire)"
                         % (name, got))


# --------------------------------------------------------------------------- etape B

def _titanhammer_stage(elev_by_pos=None):
    """Etat jouet portant `1573` sur un porteur et N tuiles marquees `1571` de MEME source."""
    from engine.entities import EffectsState
    from engine.entities.effect_type import EffectType
    from engine.entities.effects import EffectFactory
    from engine.runner.operations.effects import AddEffectOperation
    from engine.runner.snapshot import load_state

    carrier, caster = 10, 40
    board = _toy_board(elev_by_pos)
    decision = {"currentPlayer": 1, "units": [
        {"id": carrier, "visualId": "deathBlightlord", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 1}, "effects": []},
        {"id": caster, "visualId": "astarLysander", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 2}, "effects": []}]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": 3, "turnsStarted": 0},
                           "healthMax": 1000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in decision["units"]]}
    st = load_state(decision, observe, snapshot, board=board, ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    AddEffectOperation.execute(st, source=caster, target=carrier,
                               effect_type=H.TELEPORTING_IN,
                               name=EffectType.TitanhammerSquad_TeleportingIn.name)

    def mark(coord):
        st.effects.add_effect(int(board.id_at(coord[0], coord[1])), EffectFactory.create(
            {"name": EffectType.TitanhammerSquad_TargetTile.name,
             "effectType": H.TARGET_TILE, "source": int(caster), "remaining": 0}))

    return st, board, carrier, mark


def _marked_order(st, board, caster_id: int) -> list:
    """L'ordre d'ENUMERATION des tuiles marquees `1571` de source `caster_id`, re-derive ici (et non
    demande au port) : c'est ce premier element que le bras `Contains` regarde."""
    out = []
    for carrier, effs in (st.effects.by_unit or {}).items():
        if int(carrier) not in board.by_id:
            continue
        for e in (effs or []):
            if (not e.consumed and int(getattr(e, "effect_type", -1)) == H.TARGET_TILE
                    and e.source is not None and int(e.source) == int(caster_id)):
                out.append(int(carrier))
                break
    return out


def _cond(st, dest, uid) -> bool:
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.loki.teleporting_in import (
        TitanhammerSquadTeleportingInAddMovingOnPreMove as T4)
    ev = TriggerEvent(int(EventTriggerType.PreUnitMove), uid, uid, ranged=False, profile=None,
                      dest_tile=(None if dest is None else tuple(dest)))
    return T4(uid)._custom_moving_condition(st, ev)


def etape_b(fails: list) -> None:
    """Le foyer du residu, sur les DEUX termes de la primitive."""
    print("=== etape B -- vslot 0x748 : les deux termes foldes de la primitive ===")

    # (I) plusieurs marques, destination = une marque AUTRE que la premiere. Le bras `Contains`
    # (`Y` reduite a UNE entite par le slot 1) ne la voit pas ; le bras `IsAdjacentTiles` la voit,
    # par le COURT-CIRCUIT -- et lui seul.
    st, board, carrier, mark = _titanhammer_stage()
    marks = [(3, 3), (0, 6)]           # DISJOINTES : (0,6) n'est voisine d'aucune autre marque
    for m in marks:
        mark(m)
    # MONTAGE, pas mesure : le bras `Contains` ne lit QUE la premiere marque telle qu'elle est
    # ENUMEREE. Si la destination tombait dessus, ce bras suffirait et le test ne mesurerait rien.
    # L'ordre est re-derive ICI (iteration de `EffectsState.by_unit`), pas demande au port.
    seen = [board.coord(int(t)) for t in _marked_order(st, board, caster_id=40)]
    dest = next((m for m in marks if m != seen[0]), None) if seen else None
    if dest is None:
        fails.append("B(I) MONTAGE : le port enumere %r -- aucune marque n'est APRES la premiere, "
                     "le bras `IsAdjacentTiles` ne serait pas exerce" % (seen,))
        return
    got = _cond(st, dest, carrier)
    print("  (I) dest = une marque (marques=%r, ordre PORT=%r, dest=%r) -> %r"
          % (marks, seen, dest, got))
    if got is not True:
        fails.append("B(I) : destination EGALE a une tuile marquee -> %r. `AreTilesAdjacent(t, t)` "
                     "est VRAI, donc le bras `IsAdjacentTiles` doit passer meme quand `Contains` "
                     "(qui ne lit que la PREMIERE marque) ne passe pas" % got)

    # (E) une seule marque, destination VOISINE mais separee de 2 crans d'elevation.
    st, board, carrier, mark = _titanhammer_stage(elev_by_pos={(3, 3): 0, (3, 4): 2})
    mark((3, 3))
    nb = board.coord(board.neighbours(board.id_at(3, 3))[0])
    high = (3, 4)
    assert board.id_at(high[0], high[1]) in set(board.neighbours(board.id_at(3, 3))), \
        "MONTAGE : (3,4) n'est pas voisine de (3,3) dans cette geometrie"
    got_high = _cond(st, high, carrier)
    got_flat = _cond(st, nb if nb != high else board.coord(board.neighbours(
        board.id_at(3, 3))[1]), carrier)
    print("  (E) dest voisine a |dElev| = 2 (%r) -> %r   |   voisine PLATE (%r) -> %r"
          % (high, got_high, nb if nb != high else "autre", got_flat))
    if got_high is not False:
        fails.append("B(E) : voisine a |dElev| = 2 -> %r. La primitive rend `(dElev < 2) & b` : "
                     "2 crans FERMENT l'adjacence, quelle que soit la connectivite" % got_high)
    if got_flat is not True:
        fails.append("B(E) temoin : voisine PLATE -> %r (le bras `IsAdjacentTiles` doit passer) "
                     % got_flat)


# --------------------------------------------------------------------------- etape C

def etape_c(fails: list) -> None:
    """Le GISEMENT du terme (E). Sans ce chiffre, << la porte d'elevation mord >> reste une opinion.

    Les boards du depot stockent leurs tuiles en COLONNES (`board.Tiles[col].Tile[row]`), l'elevation
    a `Tile[row].Elevation` -- c'est le meme champ que `boardGraph` publie a plat sous `elevation`."""
    files = sorted(glob.glob(str(BOARDS / "**" / "*.json"), recursive=True))
    if not files:
        fails.append("C : aucun board sous %s -- `python dump_boards.py` regenere les entrees"
                     % BOARDS)
        return
    boards, with_span, with_pair, pair_total = 0, 0, 0, 0
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cols = (d.get("board") or {}).get("Tiles") or []
        if not cols:
            continue
        boards += 1
        elev = {}
        for ci, c in enumerate(cols):
            for ri, t in enumerate(c.get("Tile") or []):
                elev[(ci, ri)] = t.get("Elevation")
        vals = {v for v in elev.values() if v is not None}
        if vals and max(vals) - min(vals) >= 2:
            with_span += 1
        n = 0
        for (c, r), e in elev.items():
            if e is None:
                continue
            for (nc, nr) in hexgeo.neighbors(c, r):
                e2 = elev.get((nc, nr))
                if e2 is not None and abs(int(e) - int(e2)) >= 2:
                    n += 1
        if n:
            with_pair += 1
            pair_total += n // 2
    print("=== etape C -- gisement du terme (E) sur `data/boards/**` ===")
    print("  boards lus                                  : %d" % boards)
    print("  dont span d'elevation >= 2                  : %d" % with_span)
    print("  dont >= 1 paire VOISINE a |dElev| >= 2      : %d" % with_pair)
    print("  paires voisines |dElev| >= 2, tous boards   : %d" % pair_total)
    if boards == 0:
        fails.append("C : 0 board exploitable (format inattendu) -- la mesure ne dit rien")
    elif with_pair == 0:
        print("  -> le terme (E) serait INOBSERVABLE sur ce build (aucune paire voisine ecartee)")


# --------------------------------------------------------------------------- etape D (LIVE)

def _elev(board, pos) -> int:
    return int(board.elevation(board.id_at(pos[0], pos[1])))


def etape_d(board_id: str, seed_value: str, fails: list) -> None:
    """LIVE. MEME montage que #448-r2d, mais la destination est CHOISIE pour exercer (E) : une
    voisine de la marque separee de >= 2 crans. Attendu : ni le port ni le natif ne posent `1574`."""
    print("=== etape D (LIVE) -- board=%s seed=%s ===" % (board_id, seed_value))
    rid = H.build(seed_value, board_id)
    try:
        st, board = H.offline_state(H.capture(rid))
        caster = H.find_vid(st, H.CASTER)
        if caster is None:
            raise SystemExit("MONTAGE : %s non deploye" % H.CASTER)

        ab = H.rpc("abilityTargets",
                   {"runnerId": rid, "unitId": caster, "abilityType": H.ABILITY}, 180)
        tiles = [(t["tile"]["col"], t["tile"]["row"]) for u in (ab.get("units") or [])
                 for a in (u.get("abilities") or []) for t in (a.get("fromHere") or [])
                 if t.get("kind") == "tile"]
        if not tiles:
            raise SystemExit("MONTAGE : %d n'a AUCUNE tuile-cible `fromHere`" % H.ABILITY)

        # La cible du cast est choisie pour MAXIMISER l'ecart d'elevation avec une de ses voisines :
        # c'est la seule facon d'exercer (E) au lieu de le subir. Doctrine << on deplace, on ne
        # subit pas la geometrie >>.
        def _best_gap(t):
            tid = board.id_at(t[0], t[1])
            if tid is None:
                return -1
            e = int(board.elevation(tid))
            return max([abs(e - int(board.elevation(n))) for n in board.neighbours(tid)] or [-1])

        target = max(tiles, key=_best_gap)
        gap = _best_gap(target)
        print("[MONTAGE] cible du cast %r (meilleur ecart d'elevation avec une voisine = %d)"
              % (target, gap))
        r = H.rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "to": {"col": target[0], "row": target[1]},
            "abilityType": H.ABILITY}}, 180)
        if not ((r.get("actions") or [{}])[0].get("ok")):
            raise SystemExit("MONTAGE : le cast de %d a ECHOUE : %s"
                             % (H.ABILITY, json.dumps(r)[:400]))

        st, board = H.offline_state(H.capture(rid))
        marks = H.marked_tiles(st, board, caster)
        print("[MONTAGE] tuiles marquees %d : %r (cardinalite %d)"
              % (H.TARGET_TILE, marks, len(marks)))
        if len(marks) != 1:
            print("[MONTAGE] /!\\ cardinalite != 1 : le regime (I) devient observable ici")
        if not marks:
            raise SystemExit("MONTAGE : aucune marque posee")

        tid = board.id_at(marks[0][0], marks[0][1])
        me = int(board.elevation(tid))
        table = sorted((board.coord(n), int(board.elevation(n)), abs(me - int(board.elevation(n))))
                       for n in board.neighbours(tid))
        print("[MESURE] marque=%r elev=%d ; voisines (pos, elev, |dElev|) : %r"
              % (marks[0], me, table))

        mv = H.rpc("aiMovableTiles", {"runnerId": rid}, 120)
        pool = {int(u.get("unitId")): {(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])}
                for u in (mv.get("units") or [])}
        near_hi = {p for (p, _e, d) in table if d >= 2}
        movers = [uid for uid in pool
                  if any(int(getattr(e, "effect_type", -1)) == H.TELEPORTING_IN and not e.consumed
                         for e in (st.effects.by_unit.get(int(uid)) or []))]
        print("[MESURE] porteurs de 1573 mobiles : %r ; voisines de la marque a |dElev| >= 2 : %r"
              % (sorted(movers), sorted(near_hi)))

        chosen = None
        for uid in sorted(movers):
            hit = sorted(pool.get(uid, set()) & near_hi)
            if hit:
                chosen = (uid, hit[0])
                break
        if chosen is None:
            print("[NON CONFRONTE] aucune voisine de la marque a |dElev| >= 2 n'est ATTEIGNABLE "
                  "par un porteur de 1573 sur ce couple. Le terme (E) reste porte par FIDELITE ; "
                  "les elevations mesurees ci-dessus l'attestent, pas une hypothese.")
            return
        uid, dest = chosen
        print("[CONFRONTE] (E) : u%d -> %r, voisine de la marque a |dElev| = %d -- le natif NE DOIT "
              "PAS poser 1574 (le port d'avant #433-r1, qui lisait `board.neighbours` nu, en posait "
              "un)" % (uid, dest, abs(me - _elev(board, dest))))
        H.confront_arm("ARM-NEAR-ADJ-ELEV", rid, uid, dest, False, fails)
    finally:
        H._duel(["dispose", "--state-file", str(H.STATE)])


# --------------------------------------------------------------------------- main

def _mutate() -> None:
    """CONTRE-EPREUVE : on REMET le bras `IsAdjacentTiles` sur `board.neighbours` nu -- exactement
    le port d'AVANT #433-r1. Les etapes B et D DOIVENT alors rougir. Le critere est le DEPLACEMENT
    par rapport au port NON MUTE, jamais l'ecart au natif."""
    from engine.runner.operations.triggers.loki import teleporting_in as T

    def naive(self, state, ev):
        board = getattr(state, "board", None)
        if state.effects is None or board is None:
            return False
        dest = getattr(ev, "dest_tile", None)
        if dest is None:
            return False
        dest_id = board.id_at(int(dest[0]), int(dest[1]))
        if dest_id is None:
            return False
        marked = self._target_tiles(state)
        if not marked:
            return False
        if int(marked[0]) == int(dest_id):
            return True
        neigh = set(board.neighbours(int(dest_id)))
        return any(int(t) in neigh for t in marked)

    T._TitanhammerSquadTargetTileCondition._custom_moving_condition = naive
    T.TitanhammerSquadTeleportingInAddMovingOnPreMove._custom_moving_condition = naive
    print("[MUTATE] bras `IsAdjacentTiles` REMIS sur `board.neighbours` nu (ni identite, ni "
          "elevation) -- les etapes B et D DOIVENT rougir\n")


def main() -> int:
    mutated = "--mutate" in sys.argv
    if mutated:
        _mutate()
    fails: list = []
    etape_a(fails if not mutated else [])   # A ne depend pas du foyer mute
    print()
    etape_b(fails)
    print()
    etape_c(fails)
    print()
    if "--offline" not in sys.argv:
        board_id, seed_value = H.COUPLES[0]
        try:
            etape_d(board_id, seed_value, fails)
        except SystemExit as e:
            if not mutated:
                raise
            fails.append("MUTATE : %s" % e)
    print()
    if fails:
        print("=== %d ECHEC(S) ===" % len(fails))
        for f in fails:
            print("  - " + f)
        return 0 if mutated else 1
    if mutated:
        print("=== CONTRE-EPREUVE VERTE = LE PROBE NE MESURE RIEN ===")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    os.chdir(str(PYDIR))
    raise SystemExit(main())
