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
# Nombre de tuiles interrogees pour la confrontation de la REGLE DYNAMIQUE (#91). Le board entier
# serait 1 RPC par tuile ; l'echantillon en tete d'ordre de balayage porte deja les DEUX verdicts
# (aire valide / aire impossible), ce que le test VERIFIE au lieu de le supposer.
DYNAMIC_RULE_SAMPLE = 24


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

    # ETAT PRE-CAST (#91) : c'est LUI que le port rejoue. Capture APRES le placement et APRES la
    # fenetre de cooldown/tour, donc strictement l'etat que le natif s'apprete a muter.
    pre_dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    pre_ob = rpc("observeBattle", {"runnerId": rid})

    # VERDICTS de la REGLE DYNAMIQUE (#91), tuile par tuile, AVANT le cast : c'est le seul moment ou
    # la MoW peut encore etre interrogee. `abilityReason` natif == `GetInvalidTargetReason`, dont la
    # derniere marche est `DutyEternalAbility$$GetDynamicInvalidTargetReason`.
    pre_state = load_state(pre_dv, pre_ob, board=board)
    from engine.runner.abilities.ultramarines import DutyEternalAbility
    probe = DutyEternalAbility()
    reasons = []
    for pos in sorted(board.by_coord)[:DYNAMIC_RULE_SAMPLE]:
        tid = board.id_at(pos[0], pos[1])
        if tid is None:
            continue
        native = rpc("abilityReason", {"runnerId": rid, "casterId": caster,
                                       "abilityType": DUTY_ETERNAL, "targetId": tid})
        reasons.append({
            "pos": pos, "tile": tid,
            "native": " ".join(str(x) for x in (native.get("reasons") or [])),
            "port": probe.get_dynamic_invalid_target_reason(pre_state, caster, tid),
            "area": STS.get_area(board, set(_occupants(rpc, rid)), pos),
        })

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
            "actions": actions, "board": board, "uid": unit["id"], "view": after,
            # #91 -- de quoi rejouer le cast COTE PORT sur l'etat PRE-cast, et confronter la face
            # DECISION (regle dynamique) tuile par tuile.
            "caster": caster, "pre": (pre_dv, pre_ob), "reasons": reasons,
            "mow_before": mows[0]}


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


# ============================================================================================== #
# #91 -- LE PORT DE L'ABILITY (et plus seulement du substrat) : `DutyEternalAbility`.
# Les tests ci-dessus confrontent la REPRESENTATION d'une unite deja posee par le NATIF ; ceux-ci
# rejouent le cast COTE PORT sur l'etat PRE-cast et confrontent ce que le PORT produit.
# ============================================================================================== #

def _port_cast(galatian):
    """Rejoue `DutyEternal` COTE PORT sur l'etat PRE-cast (meme caster, meme tuile ciblee)."""
    from engine.runner.abilities.ultramarines import DutyEternalAbility
    pre_dv, pre_ob = galatian["pre"]
    state = load_state(pre_dv, pre_ob, board=galatian["board"])
    tile_id = galatian["board"].id_at(galatian["anchor"][0], galatian["anchor"][1])
    diag = DutyEternalAbility().execute_behaviour(state, galatian["caster"], tile_id)
    return state, diag


def test_port_ability_is_registered_with_its_literals():
    """Non-regression de registre : 1158 doit entrer avec SES DEUX donnees obligatoires, lues au
    ctor natif -- `TARGETING_OPTIONS` (masque `0x20000040000042`, forme FLAGS DIRECTS) et
    `ABILITY_ATTACK_TYPE` (3e argument d'`AActiveAbility..ctor` = 2 = Others)."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    klass = ABILITY_CLASSES.get(DUTY_ETERNAL)
    assert klass is not None, "1158 absente d'ABILITY_CLASSES"
    assert int(klass.TARGETING_OPTIONS.rules) == 0x20000040000042, \
        f"masque {hex(int(klass.TARGETING_OPTIONS.rules))} != litteral du ctor 0x20000040000042"
    assert ABILITY_ATTACK_TYPE.get(DUTY_ETERNAL) == AbilityAttackType.Others


def test_port_cast_spawns_one_unit_on_the_whole_footprint(galatian):
    """LE point du cas : `SpawnUnitOptions+0x60 = 1` -> `SpawnUnitBehaviour$$Execute` prend sa
    branche `GetTileIds(tiles)` = **UNE** unite sur les 3 tuiles, PAS 3 unites d'un pied.

    C'est le chiffre DISCRIMINANT du port de l'ability : sans le flag, la meme feuille `Spawn`
    poserait `len(area)` unites mono-tuile."""
    state, diag = _port_cast(galatian)
    assert diag.get("spawned"), f"aucun spawn cote port : {diag}"
    assert len(diag["spawned"]) == 1, \
        f"{len(diag['spawned'])} unites spawnees -- la branche `options+0x60` n'a pas ete prise"
    uid = diag["spawned"][0]
    assert get_feet_count(state, uid) == 3, "l'unite portee doit avoir 3 PIEDS"
    assert diag["feet"] == galatian["predicted"], \
        f"empreinte portee {diag['feet']} != empreinte native {galatian['predicted']}"
    assert get_main_tile(state, uid) == galatian["anchor"], "feet[0] = l'ancre = la tuile ciblee"
    # ...et l'occupation suit : les 3 tuiles sont prises par CETTE unite cote port.
    for f in galatian["predicted"]:
        assert state.unit_at(f) is state.get_entity(uid), f"port : unit_at({f}) != le summon"


def test_port_cast_matches_native_footprint_and_summon(rpc, galatian):
    """Le summon POSE PAR LE PORT et celui pose par le NATIF ont le meme visualId et la MEME
    empreinte ORDONNEE (`AddUnitOperation` : un `AddFoot` par tuile, dans l'ordre recu)."""
    _state, diag = _port_cast(galatian)
    assert diag["summon"] == SUMMON
    native = _native_feet(rpc, galatian["rid"], galatian["uid"])
    assert diag["feet"] == native, f"port {diag['feet']} != natif {native}"


def test_port_cast_removes_the_machine(galatian):
    """`RemoveMachine(caster@0x160)` -> `RemoveMachineOperation$$Execute` : la MoW quitte la
    bataille. Cote port : `MachineComponent.removed`, `UnitComponent.alive = False`, et AUCUNE de
    ses abilities n'est plus utilisable (`ActiveAbility.can_currently_be_used`). C'est le pendant
    exact de l'i2 « Galatian can no longer be used as a Machine of War for the rest of the battle »
    -- et il tombe sur `MacroPlasmaIncinerator` (1159) aussi, pas seulement sur 1158."""
    from engine.runner.components import (MachineComponent, UnitComponent,
                                          ActiveAbilitiesComponent)
    state, diag = _port_cast(galatian)
    assert diag["removed_machine"] == [galatian["caster"]], \
        f"RemoveMachine n'a pas vise le caster : {diag}"
    mow = state.get_entity(galatian["caster"])
    assert mow.get_component(MachineComponent).removed is True
    assert mow.get_component(UnitComponent).alive is False
    ac = mow.get_component(ActiveAbilitiesComponent)
    if ac is not None:
        assert ac.abilities, "la MoW doit porter ses abilities (seed decisionView)"
        for a in ac.abilities:
            assert not a.can_currently_be_used(), \
                f"ability {a.ability_type} encore utilisable apres RemoveMachine"


def test_native_machine_is_gone_after_the_cast(rpc, galatian):
    """Contrepartie LIVE du test precedent -- ce que le NATIF montre de la MoW retiree : plus
    aucune de ses abilities n'est castable. On lit `decisionView.mows` APRES le cast."""
    after = rpc("decisionView", {"runnerId": galatian["rid"], "allAbilities": True})
    row = next((m for m in (after.get("mows") or [])
                if m.get("casterId") == galatian["caster"]), None)
    if row is None:
        return                                     # la MoW a DISPARU de la vue : verdict encore + net
    usable = [a for a in (row.get("abilities") or [])
              if a.get("usable") and a.get("hasAmmo", True) and not (a.get("cooldown") or 0)]
    assert not usable, \
        f"la MoW retiree expose encore des abilities castables : {json.dumps(usable)[:300]}"


def test_port_cast_grants_the_stationary_trait(galatian):
    """`AddTrait(ActiveTarget@0x180, 0x418)` = `UnitTrait.Stationary` (1048), pose PAR le
    sous-behaviour on-appearance des `SpawnUnitOptions` -- **pas** une propriete de la config du
    summon (`gameconfig(ultraSmnDreadnought).traits` ne le porte pas). C'est le « **stationary**
    unit » de l'i2, et le consommateur natif est le gate `HasTrait(0x418)` de
    `MovementQuery$$GetMovablePositionsFor`."""
    import gameconfig as GC
    from engine.entities.traits.unit_trait import UnitTrait, has_trait
    from engine.runner.components import StatsComponent
    assert UnitTrait.Stationary.name not in ((GC.unit(SUMMON) or {}).get("traits") or []), \
        "si la config portait deja Stationary, ce test ne prouverait rien"
    state, diag = _port_cast(galatian)
    sc = state.get_entity(diag["spawned"][0]).get_component(StatsComponent)
    assert has_trait(sc.ctx.traits, UnitTrait.Stationary), \
        f"trait Stationary absent du summon porte : {sc.ctx.traits}"
    # ...et le port doit en tirer la MEME conclusion que le natif : le gate `HasTrait(0x418)` en
    # tete de `MovementQuery$$GetMovablePositionsFor` rend un ensemble VIDE de positions -- gate
    # desormais reproduit (#91 ferme le residu R30 §6.3, faute de porteur jusqu'ici).
    assert MQ.get_movable_positions_for(state.board, state, diag["spawned"][0],
                                        [galatian["anchor"]]) == []


def test_port_cast_transfers_no_triggered_ability_when_caster_has_none(galatian):
    """Branche CONDITIONNELLE `if (Count > 0)` : le Galatian MoW de ce build n'a AUCUNE triggered
    ability (son seul candidat serait la MYTHIC `WisdomOfTheAncients`, absente au rang courant), la
    collection est donc vide et NI le natif NI le port ne transferent quoi que ce soit. Ce test
    VERROUILLE la degradation : `transferred_ability is None` -> aucune ability inventee sur le
    summon. La branche « non vide » reste NON CONFRONTEE LIVE (residu nomme, case-91 §7)."""
    from engine.runner.abilities.behaviours import first_triggered_ability_of
    from engine.runner.components import TriggeredAbilityComponent
    state, diag = _port_cast(galatian)
    assert first_triggered_ability_of(state, galatian["caster"]) is None, \
        "le Galatian MoW ne doit porter aucune triggered ability dans ce build"
    assert diag["transferred_ability"] is None
    tc = state.get_entity(diag["spawned"][0]).get_component(TriggeredAbilityComponent)
    assert tc is None or not tc.entries, \
        f"une triggered ability a ete inventee sur le summon : {tc.entries}"


# ------------------------------------------------- face DECISION : la REGLE DYNAMIQUE de l'ability

def test_dynamic_rule_agrees_with_native_tile_by_tile(galatian):
    """`DutyEternalAbility$$GetDynamicInvalidTargetReason` = « la tuile visee est legale SSI une
    aire triangulaire de 3 tuiles existe autour d'elle ». Confrontation TUILE PAR TUILE du verdict
    du port contre `abilityReason` natif (= `GetInvalidTargetReason`, dont la derniere marche EST
    cette regle).

    Le test EXIGE que l'echantillon porte les DEUX verdicts : sans tuile refusee il ne prouverait
    rien (un port qui dirait toujours « valide » passerait)."""
    rows = galatian["reasons"]
    assert rows, "aucun verdict collecte"
    accepted = [r for r in rows if not r["port"]]
    refused = [r for r in rows if r["port"]]
    assert accepted and refused, \
        (f"echantillon non discriminant : {len(accepted)} acceptees / {len(refused)} refusees "
         f"-- augmenter DYNAMIC_RULE_SAMPLE")
    bad = []
    for r in rows:
        native_refuses = bool(r["native"].strip())
        port_refuses = bool(r["port"])
        if native_refuses != port_refuses:
            bad.append((r["pos"], r["native"], r["port"], r["area"]))
    assert not bad, ("desaccord natif/port sur la legalite de la tuile : "
                     + "; ".join(f"{p} natif='{n}' port={q} aire={a}" for p, n, q, a in bad))


def test_dynamic_rule_refuses_exactly_when_no_area_exists(galatian):
    """Le CONTENU de la regle, pas seulement son verdict : le port refuse EXACTEMENT les tuiles ou
    `ThreeUnitSpawnTileShapeSelector$$GetArea` rend une liste vide, et le code rendu est le
    litteral `2` (`TargetingRule.TargetMatchesDynamicRule`)."""
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    for r in galatian["reasons"]:
        if r["area"]:
            assert r["port"] == 0, f"{r['pos']} porte une aire {r['area']} et le port refuse"
        else:
            assert r["port"] == int(TR.TargetMatchesDynamicRule), \
                f"{r['pos']} sans aire : le port doit rendre 2, il rend {r['port']}"
