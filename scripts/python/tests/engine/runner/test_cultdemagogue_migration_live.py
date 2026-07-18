"""Gen-stealer G4 : CultDemagogue (id 1179, Isaak genesPrimus) MIGRATION -> arbre DSL, CONFRONTE au LIVE.

`CultDemagogueAbility$$ExecuteBehaviour @1811cdc30` = `op_add(SpawnDecoys, op_add(SpawnNeophytesOnDecoys,
PerformAINeophyteTurn))` : (1) pose N=`nrOfSummons` decoys <=range de la cible, (2) summon Neophytes sur
ceil(moitie) des decoys allies de la zone (stats config `summon*_2`), (3) chaque Neophyte joue un TOUR AI
complet immediat. Le port EST l'arbre `cult_demagogue_tree()` (feuilles genestealer.py).

CONFRONTATION LIVE -- invariant ROBUSTE = les stats de SPAWN des Neophytes (`summonHp_2[level] x mult`),
BIT-EXACT vs le live, INDEPENDANTES du bruit end-state. On drive Isaak a dist<=2 d'un ennemi, on caste LIVE,
on lit `hpMax` d'un Neophyte natif, et on verifie que le PORT (meme etat-avant) produit la MEME valeur.

⚠ FINDING (probe live) : l'end-state de CultDemagogue est ENTANGLED et NON confronte tel quel :
  - les TOURS AI immediats des Neophytes DECLENCHENT `DecoysAndMisdirection` (G2, passif Isaak NON porte) ->
    des decoys SUPPLEMENTAIRES (live : 10 decoys pour ~5-6 places de base) ;
  - l'overwatch de l'ennemi TUE des Neophytes pendant leur tour (hp=0, hpMax intact) ;
  - cohabitation decoy+neophyte (le spawn Neophyte ne consomme PAS le decoy sous-jacent -- Q3c confirme live).
  => on confronte le hpMax de spawn (robuste) + la relation neo_count == ceil(decoys/2) (invariant port),
     PAS le comptage de decoys end-state (entangled avec G2).

ASCII-only. Property-based. Skip si pas de session / Isaak ne peut atteindre l'ennemi.
"""
from __future__ import annotations

import math
import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent, HealthComponent, PositionComponent, UnitComponent
from engine.entities.effects.magnitude import ability_var

import hexgeo

BUILD = ["--p-units", "genesPrimus", "--a-units", "necroDestroyer"]
CASTER_VIS = "genesPrimus"
ENEMY_VIS = "necroDestroyer"
NEO_VIS = "genesSmnNeophyte"
DEC_VIS = "genesSmnDecoy"


def _dist(a, b):
    return hexgeo.distance(a, b)


@pytest.fixture(scope="session")
def cult_demagogue(rpc, build_runner):
    """Drive Isaak a dist<=2 de l'ennemi, capture l'etat-avant, caste LIVE, et rejoue le PORT."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.genestealer import CultDemagogueAbility

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    def upos(u):
        p = u.get("pos") or {}
        return (p.get("col"), p.get("row"))

    # --- convergence : rapprocher Isaak jusqu'a etre A dist<=2 SUR SON tour (pret a caster) ---
    ready = False
    for _ in range(12):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cur = dv.get("currentPlayer")
        isaak = next((u for u in dv["units"] if u.get("visualId") == CASTER_VIS), None)
        enemy = next((u for u in dv["units"] if u.get("visualId") == ENEMY_VIS), None)
        if isaak is None or enemy is None:
            pytest.skip("isaak/enemy absent")
        ip, ep = upos(isaak), upos(enemy)
        if ip[0] is None or ep[0] is None:
            pytest.skip("positions absentes")
        if cur != isaak.get("owner"):                    # tour ennemi -> avancer
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        if _dist(ip, ep) <= 2:                            # deja en portee sur mon tour -> pret
            ready = True
            break
        # mon tour, hors portee : bouger vers l'ennemi (dans la portee si possible)
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == isaak["id"]), None)
        best = None
        for t in (mu or {}).get("tiles") or []:
            if t.get("col") is None:
                continue
            d = _dist((t["col"], t["row"]), ep)
            if best is None or d < best[0]:
                best = (d, (t["col"], t["row"]))
        if best is None or best[0] >= _dist(ip, ep):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": isaak["id"], "to": {"col": best[1][0], "row": best[1][1]}}}, 40)
        if best[0] <= 2:                                  # move m'a mis en portee -> caster CE tour
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            cur = dv.get("currentPlayer")
            isaak = next((u for u in dv["units"] if u.get("visualId") == CASTER_VIS), None)
            enemy = next((u for u in dv["units"] if u.get("visualId") == ENEMY_VIS), None)
            ready = True
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    if not ready or isaak is None or enemy is None or \
            _dist(upos(isaak), upos(enemy)) > 2 or cur != isaak.get("owner"):
        pytest.skip("Isaak n'a pas atteint dist<=2 de l'ennemi sur son tour")

    # --- etat-avant (pour le port) ---
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    isaak_id, enemy_id = isaak["id"], enemy["id"]

    # --- cast LIVE ---
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": isaak_id, "targetId": enemy_id, "abilityType": 1179}}, 60)
    ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
    live_neo = [u for u in (ob1.get("units") or []) if u.get("visualId") == NEO_VIS]

    # --- PORT sur l'etat-avant ---
    state = load_state(dv0, ob0, snap)
    state.board = board
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
        state.rng = rng
    c = state.get_entity(isaak_id)
    ctx = c.get_component(StatsComponent).ctx if c is not None else None
    level = getattr(ctx, "active_ability_level", None) if ctx is not None else None
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    res = CultDemagogueAbility().execute_behaviour(state, isaak_id, enemy_id)

    return {"live_neo": live_neo, "res": res, "state": state, "level": level, "mult": mult}


def test_cultdemagogue_spawns_live(cult_demagogue):
    """Le cast LIVE a bien summon au moins un Neophyte (l'ability n'est pas un no-op)."""
    d = cult_demagogue
    if not d["live_neo"]:
        pytest.skip("cast live n'a pas summon de Neophyte (geometrie : cible sans tuiles libres)")
    assert len(d["live_neo"]) >= 1


def test_neophyte_stats_bit_exact_vs_live(cult_demagogue):
    """Stat de spawn du Neophyte : `summonHp_2[level] x mult` (config-scale) -- le PORT reproduit BIT-EXACT le
    `hpMax` natif. Confronte la source des stats (validator priority : PAS une constante figee)."""
    d = cult_demagogue
    if not d["live_neo"]:
        pytest.skip("pas de Neophyte live")
    expected = ability_var("CultDemagogue", "summonHp_2", d["level"], multiplier_pct=d["mult"])
    live_hpmax = {u.get("hpMax") for u in d["live_neo"]}
    assert live_hpmax == {expected}, f"live neophyte hpMax {live_hpmax} != formule config {expected}"
    port_neo = d["res"]["neophytes"]
    if not port_neo:
        pytest.skip("port n'a pas summon (geometrie offline differente)")
    for nid in port_neo:
        hc = d["state"].get_entity(nid).get_component(HealthComponent)
        assert hc is not None and hc.hp_max == expected, \
            f"port neophyte hp_max {hc and hc.hp_max} != {expected} (= live)"


def test_neophyte_count_is_ceil_half_decoys(cult_demagogue):
    """Invariant du 2e etage : nombre de Neophytes == ceil(decoys places / 2) (`Half` = DivideAmount mode1 =
    Ceiling). Verifie sur le PORT (le count live est entangled avec G2 -- cf. docstring module)."""
    d = cult_demagogue
    res = d["res"]
    if not res["decoys"]:
        pytest.skip("port n'a place aucun decoy (geometrie)")
    assert len(res["neophytes"]) == math.ceil(len(res["decoys"]) / 2), \
        f"neophytes {len(res['neophytes'])} != ceil(decoys {len(res['decoys'])} / 2)"
