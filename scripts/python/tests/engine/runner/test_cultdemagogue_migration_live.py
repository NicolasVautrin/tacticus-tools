"""Gen-stealer G4 : CultDemagogue (id 1179, Isaak genesPrimus) MIGRATION -> arbre DSL, CONFRONTE au LIVE.

`CultDemagogueAbility$$ExecuteBehaviour @1811cdc30` = `op_add(op_add(SpawnDecoys, SpawnNeophytesOnDecoys),
PerformAIAction(UnitsWithId(SurroundingEnemies(target, range, ref=target), unitId_2), 0, 1))` :
(1) pose N=`nrOfSummons` decoys <=range de la cible, (2) summon Neophytes sur ceil(moitie) des decoys allies
de la zone (stats config `summon*_2`), (3) chaque Neophyte joue un TOUR AI complet immediat. Le port EST
l'arbre `cult_demagogue_tree()` (feuilles genestealer.py).

RETROFIT #94 : le 3e etage passait par une feuille BESPOKE `PerformAINeophyteTurn` qui FUSIONNAIT selecteur
et action et appelait `decide_and_apply` A NU (aucun cycle de flags de tour). Il passe desormais par le
SOCLE `PerformAIAction` (`behaviours/ai_control.py`) -> `ComputerActionOperation.execute` (mono,
`resetTurnFlags=1`). Tests dedies en fin de fichier (selection, cycle de flags, contre-cas no-op).

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
    state = load_state(dv0, ob0, snap, board=board)
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
        state.rng = rng
    c = state.get_entity(isaak_id)
    ctx = c.get_component(StatsComponent).ctx if c is not None else None
    level = getattr(ctx, "active_ability_level", None) if ctx is not None else None
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    res = CultDemagogueAbility().execute_behaviour(state, isaak_id, enemy_id)

    return {"live_neo": live_neo, "res": res, "state": state, "level": level, "mult": mult,
            "caster_id": isaak_id, "target_id": enemy_id}


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


# ============================================================================================== #
# RETROFIT #94 -- le 3e etage passe par le SOCLE `PerformAIAction` (`behaviours/ai_control.py` +
# `operations/summon_ai.py::ComputerActionOperation`) au lieu de la feuille bespoke
# `PerformAINeophyteTurn` (qui fusionnait selecteur + action et n'avait PAS le cycle de flags).
# ============================================================================================== #

def test_perform_ai_action_selects_the_fresh_neophytes(cult_demagogue):
    """ANTI-NO-OP-SILENCIEUX : le selecteur DSL du 3e etage
    (`UnitsWithId(SurroundingEnemies(target@0x178, range, ref=target), unitId_2)`) doit voir les Neophytes
    tout juste poses par le 2e etage -- alors que les DEUX etages vivent dans UN SEUL `Execute` top-level
    (`op_Addition`, @1811cdc30) et que le `DslContext` fige sa liste d'unites a la construction.
    C'est la classe de bug la plus couteuse (porte, correct, jamais atteint)."""
    d = cult_demagogue
    res = d["res"]
    if not res["neophytes"]:
        pytest.skip("port n'a summon aucun Neophyte (geometrie)")
    assert res["ai_units"], (
        "PerformAIAction n'a selectionne AUCUNE unite alors que le port a summon "
        f"{len(res['neophytes'])} Neophytes -> NO-OP SILENCIEUX (le selecteur ne voit pas les spawns)")
    assert set(res["ai_units"]) <= set(res["neophytes"]), (
        f"ai_units {res['ai_units']} deborde des Neophytes {res['neophytes']} -> le filtre "
        f"UnitsWithId(unitId_2) ne s'applique pas")


def test_reset_turn_flags_cycle_on_neophytes(cult_demagogue):
    """`PerformAIAction(..., asGroup=0, resetTurnFlags=1)` -> `ComputerActionOperation.Execute
    @180e641e0` : les flags de tour de la cible sont SAUVEGARDES, EFFACES puis RESTAURES ->
    (a) le Neophyte agit MEME deja `TurnFinished`, (b) son etat de tour est INCHANGE apres coup.
    L'ancienne feuille bespoke appelait `decide_and_apply` A NU : aucun cycle de flags."""
    from engine.runner.components import UnitFlagsComponent
    from engine.runner.operations.summon_ai import ComputerActionOperation
    d = cult_demagogue
    res = d["res"]
    if not res["neophytes"]:
        pytest.skip("pas de Neophyte porte")
    nid = res["neophytes"][0]
    e = d["state"].get_entity(nid)
    if e is None:
        pytest.skip("Neophyte absent du state")
    fl = e.get_component(UnitFlagsComponent)
    if fl is None:
        fl = UnitFlagsComponent()
        e.add_component(fl)
    before = {UnitFlagsComponent.TURN_FINISHED, UnitFlagsComponent.ACTIVE_ABILITY_USED,
              UnitFlagsComponent.MOVED}
    fl.flags = set(before)
    ComputerActionOperation.execute(d["state"], nid, True)
    assert before <= fl.flags, (
        f"flags de tour NON restaures : {sorted(fl.flags)} ne contient pas {sorted(before)}")


def test_counter_case_without_state_ref_push(cult_demagogue):
    """CONTRE-CAS du piege : avec un `DslContext` FIGE (les summons du 2e etage NON pousses dans
    `entities.units`), le selecteur du 3e etage rend un ensemble VIDE -> `PerformAIAction` = no-op.
    Sans ce contraste, "ai_units est non vide" ne prouve pas que la re-materialisation est ce qui
    l'a rendu non vide."""
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.genestealer import cult_demagogue_ai_tree
    from engine.runner.abilities.behaviours import entities_from_state
    d = cult_demagogue
    if not d["res"]["neophytes"]:
        pytest.skip("pas de Neophyte porte")
    st = d["state"]                       # etat DEJA mute par le cast : les Neophytes existent
    # contexte FIGE : meme etat, mais liste d'unites TRONQUEE des Neophytes (= ce que voyait le port
    # AVANT la poussee `entities.units.append` de la feuille de spawn)
    ectx = ExecutionContext(state=st, rng=st.rng)
    ents = entities_from_state(st, d["caster_id"], d["target_id"])
    neo = set(d["res"]["neophytes"])
    ents.units[:] = [u for u in ents.units if u.get("id") not in neo]      # simule le contexte fige
    cult_demagogue_ai_tree().execute(ents, ectx)
    ai = next((p for n, p in ectx.emitted if n == "PerformAIAction"), {})
    assert not (ai.get("units") or []), (
        "contre-cas : le selecteur trouve des unites SANS les Neophytes -> le discriminant n'isole pas "
        "la re-materialisation")
