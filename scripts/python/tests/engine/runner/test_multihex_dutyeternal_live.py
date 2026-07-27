"""R30 -- CONFRONTATION LIVE du substrat MULTI-HEX : une unite a 3 pieds, natif vs port.

CRITERE : « une unite occupant N tuiles est-elle representee, positionnee et ciblee par le port
comme par le natif ? » Ce module y repond sur le SEUL porteur multi-hex confrontable du build.

PORTEUR (verifie) : `ultraDreadnought` (Galatian) est une MoW du POOL
(`rl_duel build --list-pool` -> "8 MoW spawnables"). Son ability `DutyEternal` (1158) est
`RemoveMachine + Spawn(ThreeTileUnitSpawnShape)` -> `ultraSmnDreadnought` apparait sur **3 tuiles**.
`munitionsCost = 3` (levier : `BC.Player.Players[*].MachineOfWarAmmo`, comme probe_129/#117) et
`initialCooldownTurns = 2` (levier : on fait tourner les tours).
`AetherStride` (1208, `thousDaemonPrince`) est l'AUTRE producteur du meme `ThreeTileUnitSpawnShape` ;
il exige `catalog_inject` (porteur hors seed BC) -> non exerce ici.

CANAUX DE MESURE — tous EXISTANTS, aucun nouveau hook :
  * `observeBattle.units[]`            -> **UNE LIGNE PAR PIED** (`entityId` du pied, `squadId` de
    l'unite, col/row). L'ORDRE des pieds se derive de l'`entityId` croissant : `AddUnitOperation`
    cree chaque pied DANS la boucle d'`AddFoot` avec un id monotone -> `feet[0]` = la MAIN TILE.
    ⚠ `decisionView.units[].pos` NE convient PAS : il DEDUPLIQUE par unite et rend le DERNIER
    pied ((3,2) pour un Galatian ancre en (2,1)) ;
  * `applyAction.actions[].changes[]`  -> les tuiles ou l'unite APPARAIT (une entree par pied) ;
  * `applyAction.actions[].events[]`   -> tags `Unit_Foot_Tile_Id_1/2/3` du spawn ;
  * `boardGraph.tiles[].occupantUnitId`-> l'OCCUPATION native, tuile par tuile ;
  * `abilityReason`                    -> `GetInvalidTargetReason` natif (verdict de PORTEE).

Ce que le port doit reproduire (fonctions citees dans chaque assertion) :
  `BattleQuery$$GetTilesInTriangleShape` + `ThreeUnitSpawnTileShapeSelector$$GetArea` (la FORME),
  `UnitComponent$$AddFoot` / `UnitExtensions$$GetFeetCount` (le STOCKAGE),
  `EntityExtensions$$GetMainTileId` (l'ANCRE), `TileExtensions$$CanAddUnit` (l'OCCUPATION),
  `MovementQuery$$GetDistance` (la PORTEE, MIN sur les pieds).
ASCII only.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import hexgeo
import pytest

from engine.entities.pathfinding.board import Board
from engine.runner.components import get_feet_count, get_main_tile, get_unit_feet
from engine.runner.snapshot import load_state
from engine.services import movement_query as MQ
from engine.services import spawn_tile_shape as STS

MOW = "ultraDreadnought"
SUMMON = "ultraSmnDreadnought"
DUTY_ETERNAL = 1158
ROOT = Path(__file__).resolve().parents[5]          # racine repo (scripts/python/tests/engine/runner)
MAX_ROUNDS = 8


def _ammo_seed_bc(ammo: int = 9) -> Path:
    """Seed BC + munitions de MoW. Le seed partage part a `MachineOfWarAmmo = 0` -> aucune MoW ne
    caste (meme levier que `test_storm_speeder_live` / probe_129). Ecrit sous `logs/` (jamais
    `data/`, qui ne contient que des ENTREES versionnees)."""
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:          # Environment exclu
            p["MachineOfWarAmmo"] = ammo
    out = ROOT / "logs" / "runners" / f"bc-r30-{uuid.uuid4().hex[:8]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def _board(rpc, rid) -> Board:
    g = rpc("boardGraph", {"runnerId": rid})
    return Board(g["tiles"])


def _occupants(rpc, rid) -> dict:
    """`{(col,row): occupantUnitId}` — l'OCCUPATION NATIVE, telle que le moteur l'ecrit."""
    g = rpc("boardGraph", {"runnerId": rid})
    return {(t["col"], t["row"]): t["occupantUnitId"] for t in g["tiles"]
            if t.get("occupantUnitId") is not None}


def _native_feet(rpc, rid, uid) -> list:
    """L'EMPREINTE NATIVE ORDONNEE : lignes `observeBattle` de l'unite, triees par `entityId` du
    PIED (== ordre d'`AddFoot` == ordre de `UnitComponent._feet`, cf. `AddUnitOperation$$Execute`)."""
    rows = [(u.get("entityId") or 0, (u["col"], u["row"]))
            for u in (rpc("observeBattle", {"runnerId": rid}).get("units") or [])
            if u.get("squadId") == uid and u.get("col") is not None]
    return [t for _e, t in sorted(rows, key=lambda x: x[0])]


def _foot_tiles_from_events(actions, board) -> list:
    """L'ORDRE natif des pieds : tags `Unit_Foot_Tile_Id_1..N` de l'event de spawn (step 10)."""
    for a in actions:
        for ev in (a.get("events") or []):
            try:
                tags = json.loads(ev.get("tags") or "{}")
            except ValueError:
                continue
            ids = [tags[k] for k in sorted(tags) if k.startswith("Unit_Foot_Tile_Id_")]
            if ids:
                return [board.coord(int(i)) for i in ids]
    return []


def _pick_anchor(board, occupied, attackers) -> tuple:
    """Choisit (ancre, poste d'observation) pour rendre le scenario STRICTEMENT DISCRIMINANT.

    On veut un ATTAQUANT a distance 1 d'un pied, et a distance >= 2 des DEUX tuiles qu'un port
    mono-tuile pourrait prendre pour « la » position de l'unite :
      * `feet[0]`  = la main tile REELLE (`EntityExtensions$$GetMainTileId`) ;
      * `feet[-1]` = ce que rend `decisionView.units[].pos` (dedup du projecteur par-pied).
    Quel que soit le pied qu'un port naif retienne, il conclut « hors de portee » la ou le natif
    conclut « en portee ».

    `attackers` = les positions CANDIDATES de l'attaquant. On ne se contente PAS de la ou il se
    trouve : la geometrie de spawn de MC1_67 n'offre AUCUN couple fort avec les positions initiales
    (mesure), donc l'appelant fournit aussi les tuiles ou il peut se RENDRE (`aiMovableTiles`) et
    l'y deplace. Repli documente : critere faible, puis premiere ancre valide.
    Renvoie `(anchor, area, attacker_pos, strict)`."""
    weak = any_area = None
    for pos in sorted(board.by_coord):
        area = STS.get_area(board, occupied, pos)
        if len(area) != 3:
            continue
        if any_area is None:
            any_area = (pos, area, None, False)
        for a in attackers:
            if a in area:
                continue                              # l'attaquant occuperait un pied
            dists = [hexgeo.distance(f, a) for f in area]
            if min(dists) != 1:
                continue
            if dists[0] >= 2 and dists[-1] >= 2:
                return pos, area, a, True             # cas FORT : on s'arrete la
            if dists[0] == 2 and weak is None:
                weak = (pos, area, a, False)
    return weak or any_area or (None, None, None, False)


@pytest.fixture(scope="module")
def galatian(rpc, build_runner):
    """Monte une bataille, fait caster `DutyEternal` a la MoW, et rend tout ce qu'il faut pour
    confronter : l'ancre choisie OFFLINE, l'aire PREDITE par le port, et la reponse du natif."""
    bc = _ammo_seed_bc()
    # MoW cote ADVERSE : le Galatian spawne alors dans l'equipe 2, donc MES unites peuvent le
    # CIBLER (le volet portee a besoin d'un attaquant ennemi de la cible) et je garde la main
    # totale sur leurs deplacements — c'est ce qui rend le poste d'observation atteignable.
    rid = build_runner("777", extra=["--seed-bc", str(bc), "--a-mow", MOW, "--no-ai",
                                     "--p-units", "ultraTitus,ultraCalgar",
                                     "--a-units", "necroWarden,necroSpyder"])["rid"]

    view = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    mows = [m for m in (view.get("mows") or []) if m.get("visualId") == MOW]
    if not mows:
        pytest.fail(f"{MOW} absent de decisionView.mows -- la MoW n'est pas deployee", pytrace=False)
    caster = mows[0]["casterId"]

    board = _board(rpc, rid)
    occupied = set(_occupants(rpc, rid))
    # ATTAQUANT = une de MES unites (melee). Ses positions candidates = la ou elle est + toutes les
    # tuiles ou elle peut aller CE TOUR (`aiMovableTiles`) -> on DEPLACE pour obtenir la geometrie
    # voulue au lieu de subir les spawns.
    mine = [u for u in (view.get("units") or []) if u.get("ctrl") and u.get("pos") and u.get("alive")]
    if not mine:
        pytest.fail("aucune unite controlee pour servir d'attaquant", pytrace=False)
    attacker = mine[0]
    here = (attacker["pos"]["col"], attacker["pos"]["row"])
    mv = rpc("aiMovableTiles", {"runnerId": rid}) or {}
    reach = [here] + [(t["col"], t["row"]) for e in (mv.get("units") or [])
                      if e.get("unitId") == attacker["id"] for t in (e.get("tiles") or [])]
    anchor, predicted, post, strict = _pick_anchor(board, occupied, reach)
    if anchor is None:
        pytest.fail("aucune ancre ne porte d'aire 3-tuiles valide sur ce board", pytrace=False)
    if post is not None and post != here:
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": attacker["id"], "to": {"col": post[0], "row": post[1]}}})
        acts = r.get("actions") or []
        if not (acts and acts[0].get("ok") and acts[0].get("mutated")):
            pytest.fail(f"deplacement de l'attaquant vers {post} refuse : {json.dumps(r)[:300]}",
                        pytrace=False)
        occupied = set(_occupants(rpc, rid))
        again = STS.get_area(board, occupied, anchor)
        if again != predicted:
            pytest.fail(f"l'aire en {anchor} a change apres le deplacement : {again} != {predicted}",
                        pytrace=False)

    # DEUX conditions avant de caster, et la seconde a deja fait echouer une passe en silence :
    #  1. `initialCooldownTurns = 2` -> on fait tourner les tours jusqu'a `cooldown = None` ;
    #  2. c'est le TOUR DU PROPRIETAIRE de la MoW. Sinon `applyAction` rend `ok: true` avec
    #     `mutated: false, spawned: 0, actionConsumed: false` -- un REFUS SILENCIEUX.
    owner = mows[0].get("owner")
    for _ in range(2 * MAX_ROUNDS):
        v = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
        ab = next((a for a in (v["mows"][0].get("abilities") or [])
                   if a.get("id") == DUTY_ETERNAL), None)
        if ab is None:
            pytest.fail("DutyEternal (1158) absente des abilities de la MoW", pytrace=False)
        ready = ab.get("usable") and ab.get("hasAmmo", True) and not (ab.get("cooldown") or 0)
        if ready and (owner is None or v.get("currentPlayer") == owner):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
    else:
        pytest.fail(f"1158 jamais castable apres {2 * MAX_ROUNDS} fins de tour", pytrace=False)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": DUTY_ETERNAL,
        "to": {"col": anchor[0], "row": anchor[1]}}})
    actions = res.get("actions") or []
    ok = bool(res.get("ok") and actions and actions[0].get("ok")
              and actions[0].get("mutated") and actions[0].get("spawned"))
    if not ok:
        pytest.fail(f"cast 1158 sans effet en {anchor} (refus silencieux ?) : "
                    f"{json.dumps(res)[:500]}", pytrace=False)

    after = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    unit = next((u for u in (after.get("units") or []) if u.get("visualId") == SUMMON), None)
    if unit is None:
        pytest.fail(f"{SUMMON} absent apres le cast", pytrace=False)
    return {"rid": rid, "anchor": anchor, "predicted": predicted, "attacker_pos": post,
            "attacker_id": attacker["id"], "strict": strict,
            "actions": actions, "board": board, "uid": unit["id"], "view": after}


# ------------------------------------------------------------------------ FORME de l'empreinte

def test_native_footprint_matches_port_prediction(galatian):
    """`ThreeUnitSpawnTileShapeSelector$$GetArea` + `BattleQuery$$GetTilesInTriangleShape` : les
    tuiles ou le natif fait APPARAITRE l'unite sont EXACTEMENT celles que le port predit depuis la
    meme ancre et le meme board."""
    appeared = {(c["to"]["col"], c["to"]["row"])
                for a in galatian["actions"] for c in (a.get("changes") or [])
                if c.get("appeared") and c.get("to")}
    assert len(appeared) == 3, f"le natif a pose {len(appeared)} tuiles, pas 3 : {appeared}"
    assert appeared == set(galatian["predicted"]), \
        (f"ancre {galatian['anchor']} : natif {sorted(appeared)} != "
         f"port {sorted(galatian['predicted'])}")


def test_native_foot_order_matches_port_order(rpc, galatian):
    """L'ORDRE compte : `feet[0]` est la main tile (`EntityExtensions$$GetMainTileId`). Deux canaux
    natifs INDEPENDANTS doivent rendre le meme ordre que le port :
      * `observeBattle` trie par `entityId` du pied (== ordre d'`AddFoot`) ;
      * les tags `Unit_Foot_Tile_Id_1..3` de l'event de spawn."""
    native = _native_feet(rpc, galatian["rid"], galatian["uid"])
    assert native == galatian["predicted"], \
        f"ordre natif {native} != ordre port {galatian['predicted']}"
    assert native[0] == galatian["anchor"], "le 1er pied doit etre l'ANCRE (= la tuile ciblee)"
    tags = _foot_tiles_from_events(galatian["actions"], galatian["board"])
    if tags:
        assert set(tags) == set(native), f"tags de spawn {tags} != empreinte {native}"


def test_decision_view_pos_is_not_the_main_tile(galatian):
    """CONSTAT qui justifie le seed par `observeBattle` : `decisionView` deduplique les lignes
    par-pied du projecteur et rend un pied ARBITRAIRE (le dernier), pas la main tile. C'est
    exactement le piege qu'un port naif tomberait -- on le VERROUILLE ici."""
    unit = next(u for u in (galatian["view"].get("units") or [])
                if u.get("id") == galatian["uid"])
    pos = (unit["pos"]["col"], unit["pos"]["row"])
    assert pos in set(galatian["predicted"]), "decisionView.pos doit rester UN des pieds"
    assert pos == galatian["predicted"][-1], \
        f"decisionView.pos {pos} n'est pas le DERNIER pied {galatian['predicted']}"


# --------------------------------------------------------------------------------- OCCUPATION

def test_every_foot_tile_is_occupied_by_the_same_unit(rpc, galatian):
    """`TileExtensions$$CanAddUnit` lit `TileContentComponent` : une tuile sous un pied est
    OCCUPEE, et `UnitExtensions$$GetUnit(tile)` remonte a l'UNITE proprietaire. Le natif marque
    donc les 3 tuiles avec le MEME `occupantUnitId`."""
    occ = _occupants(rpc, galatian["rid"])
    owners = {occ.get(f) for f in galatian["predicted"]}
    assert owners == {galatian["uid"]}, \
        f"occupation native {[(f, occ.get(f)) for f in galatian['predicted']]}"


def test_port_state_reproduces_footprint_and_occupancy(rpc, galatian):
    """Le PORT, charge depuis le meme etat live (`load_state`), doit voir la meme empreinte, la
    meme main tile et la meme occupation. Sans le substrat, `get_feet_count` vaudrait 1 et deux
    des trois tuiles seraient LIBRES cote port."""
    rid = galatian["rid"]
    state = load_state(rpc("decisionView", {"runnerId": rid, "allAbilities": True}),
                       rpc("observeBattle", {"runnerId": rid}),
                       board=_board(rpc, rid))
    uid = galatian["uid"]
    assert get_feet_count(state, uid) == 3, "`UnitExtensions$$GetFeetCount` doit rendre 3"
    assert get_unit_feet(state, uid) == galatian["predicted"], "empreinte ET ordre"
    assert get_main_tile(state, uid) == galatian["anchor"], \
        "`EntityExtensions$$GetMainTileId` = feet[0] = l'ancre (PAS le `pos` de decisionView)"
    occupied = state.occupied_positions()
    for f in galatian["predicted"]:
        assert f in occupied, f"tuile {f} vue LIBRE par le port alors qu'un pied l'occupe"
        assert state.unit_at(f) is state.get_entity(uid), f"unit_at({f}) != Galatian"
    # les unites a 1 pied de la meme bataille restent STRICTEMENT mono-tuile
    for u in (galatian["view"].get("units") or []):
        if u.get("id") != uid and u.get("pos"):
            assert get_feet_count(state, u["id"]) == 1, \
                f"unite {u.get('visualId')} passee a >1 pied : REGRESSION du cas nominal"


def test_foot_tiles_are_excluded_from_movable_tiles(rpc, galatian):
    """Consequence OBSERVABLE de l'occupation : aucune unite ne peut se deplacer sur un pied de
    Galatian (le natif filtre par `CanAddUnit`)."""
    mv = rpc("aiMovableTiles", {"runnerId": galatian["rid"]}) or {}
    feet = set(galatian["predicted"])
    for entry in (mv.get("units") or []):
        tiles = {(t["col"], t["row"]) for t in (entry.get("tiles") or [])}
        assert not (tiles & feet), \
            f"unite {entry.get('unitId')} peut marcher sur {sorted(tiles & feet)}"


# -------------------------------------------------------------------------------------- PORTEE

def test_range_is_measured_from_the_whole_footprint(rpc, galatian):
    """`MovementQuery$$GetDistance(IList, IList)` = MIN sur toutes les paires de pieds.

    Le scenario a ete CHOISI discriminant (`_pick_anchor`) : un ennemi est a distance 1 d'un pied
    et a distance >= 2 des DEUX tuiles qu'un port mono-tuile pourrait retenir (`feet[0]` reel et
    `decisionView.pos`). Le natif juge la cible EN PORTEE d'une melee, la ou tout port « une seule
    tuile » la refuserait."""
    assert galatian["strict"], ("aucun couple (ancre, poste) STRICTEMENT discriminant trouve -- "
                                "le scenario ne prouverait rien, il faut re-crafter la bataille")
    attacker = next(u for u in (galatian["view"].get("units") or [])
                    if u.get("id") == galatian["attacker_id"])
    normal = next((a["id"] for a in (attacker.get("abilities") or [])
                   if a.get("kind") == "normal"), None)
    assert normal is not None, "l'attaquant n'expose pas son attaque normale"

    # 1) VERDICT NATIF : GetInvalidTargetReason ne doit PAS invoquer la portee.
    reason = rpc("abilityReason", {"runnerId": galatian["rid"], "casterId": attacker["id"],
                                   "targetId": galatian["uid"], "abilityType": normal})
    names = " ".join(str(x) for x in (reason.get("reasons") or []))
    assert "TargetIsInRange" not in names, \
        f"le natif refuse la portee alors que l'attaquant touche un pied : {json.dumps(reason)[:300]}"

    # 2) VERDICT PORT : la distance empreinte-a-empreinte vaut 1, la distance main-tile vaut 2.
    #    C'est le CHIFFRE DISCRIMINANT (avant/apres substrat) de tout ce lot.
    rid = galatian["rid"]
    state = load_state(rpc("decisionView", {"runnerId": rid, "allAbilities": True}),
                       rpc("observeBattle", {"runnerId": rid}),
                       board=_board(rpc, rid))
    feet = get_unit_feet(state, galatian["uid"])
    e = galatian["attacker_pos"]
    assert MQ.get_distance(feet, [e]) == 1, "distance empreinte-a-empreinte (MIN sur les pieds)"
    # ...alors qu'AUCUNE tuile unique ne suffisait : ni la vraie main tile, ni celle que
    # `decisionView` rend. C'est LE chiffre discriminant avant/apres substrat.
    assert hexgeo.distance(get_main_tile(state, galatian["uid"]), e) >= 2
    assert hexgeo.distance(feet[-1], e) >= 2
    # ...et le port doit CONCLURE comme le natif : `AreEntitiesAdjacent` (empreinte a empreinte).
    from engine.runner.abilities.targeting import are_entities_adjacent
    assert are_entities_adjacent(state.board, get_unit_feet(state, galatian["attacker_id"]), feet)
