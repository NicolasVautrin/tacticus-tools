"""#946 -- `1439 UnwaveringSentinel_CounterAttack` (passif `UnwaveringSentinel` de `custoKyrus`
<< Tyrith >>) : RIPOSTE `On(0x9 = Attack)` gatee par `Contains(ValidNormalAttackTargets(Owner,
Tiles(Owner), range = GetNumberConstant(range)), Caster)`, et dont le degat ne tombe PAS dans le
behaviour de l'effet -- il est ENFILE (`TriggerAbilityDelayed(Owner, 1449)`) puis joue au DRAIN par
l'ability elle-meme, branche `triggerType == 0x20 = Custom`.

RE + residus : `engine/runner/operations/triggers/loki/unwavering_sentinel.py`.
Litteraux du `.ctor` : `engine/entities/effects/loki/counter_attack.py`.

Scenarios CRAFTES (positions PILOTEES et ASSERTIONNEES), confrontes au LIVE par REPLAY-DIFF
RNG-seede :

 1. POSITIF -- un ennemi RANGED a distance 2 (= `constants.range`) tire sur Tyrith pendant le tour
    ADVERSE, AUCUN ennemi adjacent -> la riposte part (2 coups `Bolter`), PV offline == PV live des
    DEUX cotes. C'est aussi la garde du chemin FILE : sans l'entree
    `CUSTOM_TRIGGERED_ABILITIES[1449]`, l'enfilement ne serait jamais draine et le tireur ne
    perdrait rien.
 2. NEGATIF PORTEE -- MEME montage, tireur a distance 3 -> `ValidNormalAttackTargets(range = 2)` ne
    le contient pas -> AUCUNE riposte. C'est la premiere phrase de l'i2 (<< within range 2 >>), et
    c'est ce que l'override `range` du selecteur porte : sans lui, le port mesurerait la portee
    d'ARME de Tyrith et pourrait conclure autrement.
 3. NEGATIF << reduced to 1 >> -- tireur a distance 2 (donc DANS la portee nominale) MAIS un
    `orksNob` amene ADJACENT a Tyrith -> le clamp MELEE de `TargetingQuery$$GetRange` ramene la
    portee a 1 -> AUCUNE riposte. C'est la SECONDE phrase de l'i2, et le seul scenario qui la
    distingue de la premiere.
 4. ARMEMENT -- le flag `EffectComponent.IsActive @+0x5c` de l'instance 1439 : VRAI avant, FAUX
    apres (`& DeactivateEffect(effect)`).

⚠ **La geometrie est CALCULEE et ASSERTIONNEE, jamais esperee.**

Lit l'etat LIVE (rien de hardcode). ASCII only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.counter_attack import UnwaveringSentinelCounterAttackEffect
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.operations.triggers.loki import unwavering_sentinel as US
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test LIVE (cf. le jumeau `test_946_grim_retribution_live`).
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/hexgeo.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER : la chaine 1439 -> file -> 1449. Le chemin FILE est ce que ce test
        # garde en propre, d'ou `lifecycle` (le noeud) et `dispatch/pending` (la file + son drain).
        "scripts/python/engine/entities/effects/loki/counter_attack.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/loki/counter_attack.py",
        "scripts/python/engine/runner/operations/triggers/loki/unwavering_sentinel.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/pending.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/runner.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        # L'etage de CIBLAGE : c'est lui qui porte l'override `range` ET le clamp melee
        # << reduced to 1 >> que le troisieme scenario mesure.
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Test LIVE : il monte trois runners (`build_runner`), pilote les positions par RPC et "
              "confronte le port au natif par REPLAY-DIFF RNG-seede. Le perimetre couvre la chaine "
              "1439 -> `TriggerAbilityDelayed` -> file -> 1449 ET l'etage de ciblage, parce que "
              "c'est lui qui decide des deux scenarios NEGATIFS.",
}

CARRIER = "custoKyrus"            # Tyrith -- HERO au pool, porteur du passif `UnwaveringSentinel`
SHOOTER = "necroWarden"           # arme Range 3 (Gauss) : peut tirer a 2 ET a 3 hexes
BLOCKER = "orksNob"               # melee pur : au CONTACT, il declenche le clamp << reduced to 1 >>
EFFECT = int(EffectType.UnwaveringSentinel_CounterAttack)      # 0x59f = 1439
ABILITY = "UnwaveringSentinel"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _row(dv, uid):
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)


def _eff(u, etype):
    return next((e for e in ((u or {}).get("effects") or []) if e.get("effectType") == etype), None)


def _drive(rpc, rid, board, mover_vis, anchor_vis, want, side, turns=30):
    """Amene `mover_vis` a EXACTEMENT `want` hexes d'`anchor_vis` (ne deplace que `mover_vis`)."""
    def tile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row"))

    for _ in range(turns):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        mv, an = _alive(dv, mover_vis), _alive(dv, anchor_vis)
        if mv is None or an is None:
            return None
        dist = _bfs(board, tile(an))
        if dist.get(tile(mv)) == want:
            return want
        if dv.get("currentPlayer") != mv.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": side}, 60)
        row = next((x for x in (mt.get("units") or []) if x.get("unitId") == mv["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((row or {}).get("tiles") or [])}
        exact = [t for t in reach if dist.get(t) == want]
        pool = exact or [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = exact[0] if exact else min(pool, key=lambda t: abs(dist[t] - want))
        col, r = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": col, "row": r}}}, 40)
        if not exact:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    mv, an = _alive(dv, mover_vis), _alive(dv, anchor_vis)
    if mv is None or an is None:
        return None
    return _bfs(board, tile(an)).get(tile(mv))


def _scenario(rpc, build_runner, shoot_dist: int, with_blocker: bool):
    """Monte Tyrith vs le tireur (+ le bloqueur au contact si `with_blocker`), amene le tireur a
    `shoot_dist`, passe au tour ADVERSE, puis rejoue le TIR LIVE et OFFLINE sur la MEME graine."""
    a_units = SHOOTER if not with_blocker else "%s,%s" % (SHOOTER, BLOCKER)
    b = build_runner("777", extra=["--roster", "1", "--p-units", CARRIER,
                                   "--a-units", a_units,
                                   "--hp-player", "999999", "--hp-target", "999999",
                                   "--crit", "0,0", "--crit-target", "0,0",
                                   "--block-target", "0,0", "--block-player", "0,0"])
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        pytest.fail("boardGraph indisponible -- AUCUNE mesure n'a eu lieu")
    board = Board(bg["tiles"], adjacency="native_sym")

    def tile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row"))

    got = _drive(rpc, rid, board, CARRIER, SHOOTER, shoot_dist, "friendly")
    if got != shoot_dist:
        pytest.fail(f"pilotage: distance porteur/tireur = {got} != {shoot_dist}")
    if with_blocker:
        got_b = _drive(rpc, rid, board, BLOCKER, CARRIER, 1, "all")
        if got_b != 1:
            pytest.fail(f"pilotage: distance bloqueur/porteur = {got_b} != 1")

    for _ in range(4):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        car = _alive(dv, CARRIER)
        if car is not None and dv.get("currentPlayer") != car.get("owner"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    car, sho = _alive(dv, CARRIER), _alive(dv, SHOOTER)
    if car is None or sho is None:
        pytest.fail("unite manquante apres le setup -- AUCUNE mesure n'a eu lieu")
    if dv.get("currentPlayer") == car.get("owner"):
        pytest.fail("le tour du PORTEUR n'a pas pu etre quitte -- la fenetre n'est pas ouverte")

    d_shoot = _bfs(board, tile(sho)).get(tile(car))
    if d_shoot != shoot_dist:
        pytest.fail(f"geometrie: porteur/tireur = {d_shoot} != {shoot_dist} au moment de la mesure")
    adj = []
    for u in (dv.get("units") or []):
        if not u.get("alive") or u.get("owner") == car.get("owner"):
            continue
        if _bfs(board, tile(car)).get(tile(u)) == 1:
            adj.append(u.get("visualId"))
    if with_blocker and not adj:
        pytest.fail("geometrie: aucun ennemi adjacent alors que le scenario en exige un")
    if not with_blocker and adj:
        pytest.fail(f"geometrie: ennemi(s) adjacent(s) inattendu(s) {adj}")

    norm = next((a for a in (sho.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        pytest.fail("pas d'attaque normale sur le tireur")

    dvi = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                               "includeInactive": True}, 90)
    row_before = _eff(_row(dvi, car["id"]), EFFECT)

    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=board)
    uc = next((u.get("unitConfig") or {} for u in (snap.get("units") or [])
               if u.get("entityId") == car["id"]), {})
    plvl = uc.get("passiveAbilityLevel")
    mult = uc.get("abilityVariablesMultiplier") or 100
    hp_before = {}
    for u in (car, sho):
        e = state.get_entity(u["id"])
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is None or hc.hp is None:
            pytest.fail("unite sans PV offline")
        hp_before[u["id"]] = hc.hp
    inst = next((e for e in (state.effects.by_unit.get(car["id"]) or [])
                 if e.effect_type == EFFECT and not e.consumed), None)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.fail("dumpRng KO")
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": sho["id"], "targetId": car["id"],
        "abilityType": norm["id"]}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.fail(f"attaque live KO: {str(res)[:200]}")
    live_hp = {u.get("squadId"): u.get("hp") for u in (res.get("units") or [])}
    counter_amounts = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == sho["id"] and "Amount" in td:
            counter_amounts.append(int(td.get("Amount")))

    dvi2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                                "includeInactive": True}, 90)
    row_after = _eff(_row(dvi2, car["id"]), EFFECT)

    runner.apply(AttackUnitMessage(sho["id"], car["id"]))
    off_hp = {}
    for u in (car, sho):
        e = state.get_entity(u["id"])
        hc = e.get_component(HealthComponent) if e is not None else None
        off_hp[u["id"]] = hc.hp if hc is not None else None

    return {"ok": True, "rid": rid, "carrier": car["id"], "shooter": sho["id"],
            "hp_before": hp_before, "off_hp": off_hp, "live_hp": live_hp,
            "counter_amounts": counter_amounts, "inst": inst,
            "armed_before": row_before, "armed_after": row_after,
            "active_before": (row_before or {}).get("active"),
            "active_after": (row_after or {}).get("active"),
            "plvl": plvl, "mult": mult, "adjacent_enemies": adj, "dist": d_shoot}


@pytest.fixture(scope="module")
def positif(rpc, build_runner):
    return _scenario(rpc, build_runner, shoot_dist=2, with_blocker=False)


@pytest.fixture(scope="module")
def negatif_hors_portee(rpc, build_runner):
    return _scenario(rpc, build_runner, shoot_dist=3, with_blocker=False)


@pytest.fixture(scope="module")
def negatif_reduite_a_un(rpc, build_runner):
    return _scenario(rpc, build_runner, shoot_dist=2, with_blocker=True)


def test_instance_1439_est_materialisee_et_de_la_classe_portee(positif):
    inst = positif["inst"]
    assert inst is not None, "aucune instance 1439 materialisee sur le porteur"
    assert UnwaveringSentinelCounterAttackEffect.ACTIVATION_FREQUENCY == 1
    assert US.counter_attack_range() == 2, "la constante `range` du gameconfig doit valoir 2"


def test_riposte_positif_replay_diff(positif):
    """Le TIREUR encaisse les 2 coups Bolter, et le port les rejoue AU MEME RANG du flux RNG.

    C'est AUSSI la garde du chemin FILE : le degat ne tombe qu'apres
    `TriggerAbilityDelayed -> add_pending_triggered_ability -> drain de Runner.apply ->
    CUSTOM_TRIGGERED_ABILITIES[1449]`. Si l'un de ces maillons manquait, `off_hp` du tireur serait
    INCHANGE alors que le live l'a fait baisser."""
    r = positif
    assert r["dist"] == 2
    assert r["counter_amounts"], (
        "AUCUN degat sur le tireur cote LIVE : le natif n'a pas riposte, le montage est faux")
    for uid in (r["carrier"], r["shooter"]):
        assert r["off_hp"][uid] == r["live_hp"].get(uid), (
            f"replay-diff KO sur {uid}: offline {r['off_hp'][uid]} != live {r['live_hp'].get(uid)}")
    assert r["off_hp"][r["shooter"]] < r["hp_before"][r["shooter"]], (
        "le tireur n'a rien perdu cote OFFLINE : l'enfilement n'a pas ete draine "
        "(chemin FILE rompu, ou 1449 absente de CUSTOM_TRIGGERED_ABILITIES)")


def test_riposte_positif_deux_coups_dans_les_bornes(positif):
    """`GetHits()` = `constants.nrOfHits` = 2, et chaque montant tombe sous le plafond
    `maxDmg[niveau PASSIF] x multiplicateur`. Tyrith n'ayant PAS d'Overwatch, il n'y a pas de second
    vecteur qui frapperait le meme adversaire -- mais on garde l'attribution par principe."""
    r = positif
    mx = ability_var(ABILITY, "maxDmg", level=r["plvl"], multiplier_pct=r["mult"])
    assert mx, "borne de degat illisible au gameconfig"
    assert len(r["counter_amounts"]) == 2, (
        f"{len(r['counter_amounts'])} coup(s) de riposte au lieu de 2 (`nrOfHits`)")
    assert all(0 < a <= mx for a in r["counter_amounts"]), (
        f"montants {r['counter_amounts']} hors du plafond {mx}")


def test_armement_flag_isactive_tombe_apres_la_riposte(positif):
    r = positif
    assert r["armed_before"] is not None, (
        "1439 ABSENT du canal includeInactive AVANT le coup -- l'effet n'est meme pas pose")
    assert r["active_before"] is True, (
        "l'instance n'etait pas ARMEE avant le coup -- `On(0x12) & NOT IsTurnOf(Owner) -> "
        "ActivateEffect` n'a pas joue")
    assert r["active_after"] is False, "le flag n'est pas retombe : le DeactivateEffect n'a pas joue"


def test_negatif_hors_portee_2(negatif_hors_portee):
    """`Contains(ValidNormalAttackTargets(Owner, Tiles(Owner), range = 2), Caster)` -- a 3 hexes le
    tireur n'est PAS dans les cibles d'attaque normale de Tyrith, donc AUCUNE riposte.

    ⚠ **CE QUE CE TEST NE MESURE PAS, et c'est MESURE** (#946) : il ne separe PAS l'override
    `range = GetNumberConstant(range)` de la portee d'ARME du porteur. Contre-epreuve jouee : muter
    le port en `range = None` (donc portee d'arme) laisse ce test **VERT**, parce que le Bolter de
    `custoKyrus` a `Range = 2` -- exactement la valeur de `constants.range`. Les deux lectures
    COINCIDENT sur le seul porteur du passif, et aucun levier de montage disponible ne les separe
    (`--unit-stat` patche `BC.Units[].Weapons`, que le port ne lit pas : `unit_weapon_range` lit le
    GAMECONFIG -- residu deja nomme dans `runner/abilities/targeting.py`).
    Ce qui MORD, en revanche, c'est le conjoint de portee dans son ENSEMBLE : le neutraliser
    (`return True`) fait rougir CE test ET celui du clamp << reduced to 1 >>. Residu **#946-r2**."""
    r = negatif_hors_portee
    assert r["dist"] == 3
    assert not r["counter_amounts"], (
        f"le natif a riposte a 3 hexes ({r['counter_amounts']}) : la portee lue ne serait pas "
        "`constants.range = 2`")
    for uid in (r["carrier"], r["shooter"]):
        assert r["off_hp"][uid] == r["live_hp"].get(uid), (
            f"replay-diff KO sur {uid}: offline {r['off_hp'][uid]} != live {r['live_hp'].get(uid)}")
    assert r["off_hp"][r["shooter"]] == r["hp_before"][r["shooter"]], (
        "le port a riposte hors portee : l'override `range` n'est pas arme")


def test_negatif_portee_reduite_a_un_par_ennemi_adjacent(negatif_reduite_a_un):
    """SECONDE phrase de l'i2 : << If there is an enemy adjacent to Tyrith, the range of this ability
    is reduced to 1 >>. Le tireur est a 2 hexes -- DANS la portee nominale -- mais un ennemi est au
    contact, et le clamp MELEE de `TargetingQuery$$GetRange` ramene la portee a 1.

    C'est le SEUL scenario qui separe les deux phrases : a 2 hexes sans bloqueur la riposte part
    (cf. `test_riposte_positif_replay_diff`), a 2 hexes avec bloqueur elle ne part pas."""
    r = negatif_reduite_a_un
    assert r["dist"] == 2 and r["adjacent_enemies"], "montage: distance 2 + un ennemi au contact"
    assert not r["counter_amounts"], (
        f"le natif a riposte ({r['counter_amounts']}) alors qu'un ennemi est adjacent -- "
        "le clamp << reduced to 1 >> ne serait pas celui qui est lu")
    for uid in (r["carrier"], r["shooter"]):
        assert r["off_hp"][uid] == r["live_hp"].get(uid), (
            f"replay-diff KO sur {uid}: offline {r['off_hp'][uid]} != live {r['live_hp'].get(uid)}")
    assert r["off_hp"][r["shooter"]] == r["hp_before"][r["shooter"]], (
        "le port a riposte malgre le clamp melee")
