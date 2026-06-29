"""FinalJustice (worldKharn) — VRAI tri de cible offline (composite Damage 34), confronte aux UNITES LIVE.

Valide le port de `SortUnitsByDamageUtility` (`SortUnitsByDamageUtilitySelector.Select`@180ef4960 +
`FinalJusticeAbility.CreateBehaviour`@18121ed00) tel que RE LECTURE INTEGRALE :
  - pour chaque cible normal-attaquable, prediction de l'attaque normale -> `UtilityDecider.CalculateUtility
    (UtilityDefinition 0x22 = 34 = composite Damage)` -> Dict cible->util -> `OrderBy(util via lambda
    <Select>b__0)` -> 1ere ;
  - le lambda `<Select>b__0`@180efec40 renvoie **`Fix64.op_UnaryNegation(util)`** -> `OrderBy(-util)` =
    tri DECROISSANT -> 1ere cible = utilite **MAX** ; FinalJustice frappe donc l'**argmax** du composite
    Damage(34) = DamageDealt(35)+KillUnit(36)+OverkillUnit(37) ;
  - gate `Count(validTargets) > 0 AND NOT TargetIsOverkilled`.

PROTOCOLE (live, deterministe) : build Kharn vs >=3 ennemis ; capture l'etat REEL a turn 0 (stats/PV live).
On REPOSITIONNE les ennemis REELS sur les tuiles voisines de Kharn (positions DRIVEES offline -> adjacence
garantie ; HP/stats reels CONSERVES, cf. doctrine "drive positions"). Puis :
  • la prediction PRE-ARMURE de l'attaque normale de Kharn (ctx REEL : arme/mods/hits) est une plage > 0 ;
  • `_finaljustice_target` choisit l'ennemi d'utilite composite MAXIMALE (== argmax recalcule, tie-break id
    croissant) -> valide le SENS du tri (argmax, pas argmin) ;
  • mort NON-overkill -> FinalJustice tire (target != None, attack total > 0) ;
  • mort OVERKILL -> FinalJustice SUPPRIME (gate `NOT TargetIsOverkilled`) ;
  • sans aucun ennemi adjacent -> aucune cible (gate `Count > 0`).

L'oracle = les UNITES NATIVES live (stats/PV reels) + la definition du tri LUE dans le decompile. Le
confrontation au CHOIX que l'IA native ferait reellement a la mort (death-rattle) est gatee par un staging
fragile (mort adjacente non-overkill non pilotable) -> hors scope ici. ASCII only ; ADJACENCE = evenq.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations import triggers as T
from engine.runner.operations.triggers import after_death_triggers
from engine.runner.components import (UnitComponent, HealthComponent,
                                      OwnerComponent, PositionComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.utilities import damage_composite

KHARN = "worldKharn"
BUILD = ["--roster", "1", "--p-units", "worldKharn",
         "--a-units", "necroWarden,necroOverlord,necroSpyder,necroDestroyer"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _load(dec, ob, snap, board, rng0):
    state = load_state(dec, ob, snap)
    state.board = board
    if _ok(rng0):
        state.rng = _seed_rng(rng0)
    return state


def _reposition_enemies_adjacent(state, kid):
    """DRIVE (offline) : place les ennemis vivants REELS sur les tuiles voisines de Kharn (HP/stats reels
    conserves). Renvoie la liste des ids repositionnes."""
    board = state.board
    ke = state.get_entity(kid)
    kpc = ke.get_component(PositionComponent)
    koc = ke.get_component(OwnerComponent)
    ktile = board.id_at(kpc.col, kpc.row)
    neigh = list(board.neighbours(ktile))
    enemies = []
    for eid, e in state.entities.items():
        if eid == kid:
            continue
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        if oc is None or (koc is not None and oc.team == koc.team):
            continue
        if uc is not None and not uc.alive:
            continue
        enemies.append(eid)
    enemies = sorted(enemies)[:len(neigh)]
    for eid, tile in zip(enemies, neigh):
        col, row = board.coord(tile)
        pc = state.get_entity(eid).get_component(PositionComponent)
        if pc is not None:
            pc.col, pc.row = col, row
    return enemies


def test_finaljustice_target_sort_live(live_session, rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    kd = next((u for u in (dec.get("units") or []) if u.get("visualId") == KHARN), None)
    if kd is None:
        pytest.skip("Kharn absent de l'etat capture")
    kid = kd.get("id")

    # --- 1. NON-overkill : argmax + attaque ------------------------------------------------------
    state = _load(dec, ob, snap, board, rng0)
    if state.get_entity(kid) is None:
        pytest.skip("Kharn absent offline (snapshot incomplet)")
    enemies = _reposition_enemies_adjacent(state, kid)
    if len(enemies) < 2:
        pytest.skip("moins de 2 ennemis repositionnables (board en coin) -> tri non discriminant")

    adj = T._adjacent_enemies(state, kid)
    assert set(adj) == set(enemies), f"adjacence offline {adj} != repositionnes {enemies}"

    # prediction PRE-ARMURE sur le ctx REEL de Kharn : plage de degat sante > 0.
    rng_pred = T._normal_attack_health_range(state, kid)
    assert rng_pred is not None, "prediction d'attaque normale indispo (ctx Kharn)"
    dmin, dmax = rng_pred
    assert 0 < dmin <= dmax, f"plage de degat invalide {rng_pred}"

    # argmax INDEPENDANT (meme formule composite Damage 34, tie-break id croissant).
    wt = T._damage_utility_weights()

    def _util(eid):
        ent = state.get_entity(eid)
        hc = ent.get_component(HealthComponent)
        hp = int(hc.hp) if (hc is not None and hc.hp is not None) else 0
        mx = int(hc.hp_max) if (hc is not None and hc.hp_max) else hp
        pred = {"healthDmgMin": max(0, dmin), "healthDmgMax": max(0, dmax),
                "hpBefore": hp, "shieldBefore": 0,
                "killSure": hp > 0 and dmin >= hp, "kill": hp > 0 and dmax >= hp}
        return damage_composite(pred, mx, wt)

    argmax = sorted(adj, key=lambda e: (-_util(e), e))[0]   # max utilite, puis id croissant
    chosen = T._finaljustice_target(state, kid)
    assert chosen == argmax, f"_finaljustice_target={chosen} != argmax composite Damage {argmax}"

    # mort NON-overkill -> FinalJustice tire sur la meilleure cible, attaque effective.
    uc = state.get_entity(kid).get_component(UnitComponent)
    if uc is not None:
        uc.alive = False
    res = after_death_triggers(state, dying_id=kid, killer_id=adj[0], overkill=False)
    fj = next((r for r in res if r.get("trait") == "FinalJustice"), None)
    assert fj is not None and fj.get("target") == argmax, \
        f"FinalJustice n'a pas frappe l'argmax (res={res})"
    total = (fj.get("attack") or {}).get("total")
    assert total is not None and total > 0, f"attaque FinalJustice nulle (attack={fj.get('attack')})"

    # --- 2. OVERKILL : gate de suppression -------------------------------------------------------
    state2 = _load(dec, ob, snap, board, rng0)
    _reposition_enemies_adjacent(state2, kid)
    uc2 = state2.get_entity(kid).get_component(UnitComponent)
    if uc2 is not None:
        uc2.alive = False
    res2 = after_death_triggers(state2, dying_id=kid, killer_id=enemies[0], overkill=True)
    fj2 = next((r for r in res2 if r.get("trait") == "FinalJustice"), None)
    assert fj2 is None, f"FinalJustice aurait du etre supprime (overkill) mais a tire : {fj2}"

    # --- 3. AUCUN ennemi adjacent : gate Count > 0 -----------------------------------------------
    state3 = _load(dec, ob, snap, board, rng0)
    # NE PAS repositionner -> les ennemis sont a leur deploiement (non adjacents a Kharn).
    assert T._finaljustice_target(state3, kid) is None or not T._adjacent_enemies(state3, kid), \
        "attendu : pas d'ennemi adjacent au deploiement -> pas de cible FinalJustice"
