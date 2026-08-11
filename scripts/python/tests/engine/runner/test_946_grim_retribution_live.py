"""#946 -- `1213 GrimRetribution_CounterAttack` (passif `GrimRetribution` de `darkaHellblaster`
<< Sarquael >>) : RIPOSTE `On(0x9 = Attack)` APRES que le coup adverse a porte, gatee par
`NOT HasAdjacentEnemies(Owner)`, ARMEE au debut de CHAQUE tour ennemi.

RE + residus : `engine/runner/operations/triggers/loki/grim_retribution.py`.
Litteraux du `.ctor` : `engine/entities/effects/loki/counter_attack.py`.

Scenarios CRAFTES (positions PILOTEES et ASSERTIONNEES -- le runner est un bac a sable), confrontes
au LIVE par REPLAY-DIFF RNG-seede :

 1. POSITIF -- un ennemi RANGED a distance 2 (donc AUCUN ennemi adjacent a Sarquael, et l'attaquant
    est dans la portee Plasma 3 du porteur) tire sur Sarquael pendant le tour ADVERSE -> la riposte
    part (1 coup `Plasma`), et les PV offline == PV live des DEUX cotes.
 2. NEGATIF `NOT HasAdjacentEnemies` -- MEME montage + un `orksNob` amene ADJACENT a Sarquael. Le
    tireur est toujours a distance 2, l'attaque est la MEME -> AUCUNE riposte. C'est LE conjoint qui
    distingue ce passif de ses deux soeurs, et c'est la premiere phrase de l'i2.
 3. ARMEMENT -- le flag `EffectComponent.IsActive @+0x5c` de l'instance 1213, lu sur le canal
    `decisionView includeInactive` : VRAI avant le coup, FAUX apres (mesure DIRECTE du
    `& DeactivateEffect(effect)` de `$$CreateTargetTriggerBehaviour`).
 4. ATTRIBUTION -- les montants de la riposte sont dans les bornes `minDmg/maxDmg[niveau PASSIF] x
    multiplicateur`. Sans cette garde, << l'attaquant perd des PV >> serait VERT pour l'Overwatch de
    Sarquael, qui frappe le meme adversaire sur un AUTRE vecteur.

⚠ **La geometrie est CALCULEE et ASSERTIONNEE, jamais esperee** : chaque scenario refuse de conclure
si le pilotage n'a pas atteint la distance visee (`pytest.fail`, pas un skip).

Lit l'etat LIVE (rien de hardcode). ASCII only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.counter_attack import GrimRetributionCounterAttackEffect
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test LIVE : la cascade des `conftest.py`, sa fermeture,
        # et le montage de runner qu'elle pilote.
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
        # PROPRE A CE FICHIER : la chaine complete de la riposte 1213 -- litteraux du `.ctor`,
        # socle partage de la famille, module de triggers, registre, et les DEUX etages que le
        # gate consomme (`has_adjacent_enemies` et le foyer `_in_attack_range`).
        "scripts/python/engine/entities/effects/loki/counter_attack.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/loki/counter_attack.py",
        "scripts/python/engine/runner/operations/triggers/loki/grim_retribution.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Test LIVE : il monte deux runners (`build_runner`), pilote les positions par RPC et "
              "confronte le port au natif par REPLAY-DIFF RNG-seede. Le perimetre couvre donc la "
              "chaine de la riposte 1213 ET le harnais de montage, mais pas au-dela : aucun autre "
              "effet, aucune autre ability n'entre dans la mesure.",
}

CARRIER = "darkaHellblaster"      # Sarquael -- HERO au pool, porteur du passif `GrimRetribution`
SHOOTER = "necroWarden"           # arme Range 3 (Gauss) : peut tirer SANS etre adjacent
BLOCKER = "orksNob"               # melee pur : amene au CONTACT, il ferme `NOT HasAdjacentEnemies`
EFFECT = int(EffectType.GrimRetribution_CounterAttack)      # 0x4bd = 1213
ABILITY = "GrimRetribution"
SHOOT_DIST = 2                    # non adjacent (>1) ET dans la portee Plasma 3 du porteur


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
    """Amene `mover_vis` a EXACTEMENT `want` hexes d'`anchor_vis`, en ne deplacant QUE `mover_vis`.
    Rend la distance atteinte (ou None si une unite a disparu)."""
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


def _scenario(rpc, build_runner, with_blocker: bool):
    """Monte Sarquael vs le tireur (+ le bloqueur au contact si `with_blocker`), passe au tour
    ADVERSE, puis rejoue le TIR de l'ennemi LIVE et OFFLINE sur la MEME graine RNG."""
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

    # (1) MON unite va a `SHOOT_DIST` du tireur (je bouge SARQUAEL : son propre Overwatch ne se
    #     declenche donc pas pendant le placement -- c'est le mouvement d'un ENNEMI qui l'arme).
    got = _drive(rpc, rid, board, CARRIER, SHOOTER, SHOOT_DIST, "friendly")
    if got != SHOOT_DIST:
        pytest.fail(f"pilotage: distance porteur/tireur = {got} != {SHOOT_DIST}")
    # (2) le bloqueur vient AU CONTACT de Sarquael (c'est LUI qui bouge -> son approche peut manger
    #     un tir d'Overwatch, sans effet sur la mesure, prise APRES sur une capture RNG-seedee).
    if with_blocker:
        got_b = _drive(rpc, rid, board, BLOCKER, CARRIER, 1, "all")
        if got_b != 1:
            pytest.fail(f"pilotage: distance bloqueur/porteur = {got_b} != 1")

    # (3) tour ADVERSE = la fenetre d'armement (`On(0x12) & NOT IsTurnOf(Owner) -> ActivateEffect`)
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

    # (4) GEOMETRIE ASSERTIONNEE, pas esperee -- c'est ELLE qui rend le verdict interpretable
    d_shoot = _bfs(board, tile(sho)).get(tile(car))
    if d_shoot != SHOOT_DIST:
        pytest.fail(f"geometrie: porteur/tireur = {d_shoot} != {SHOOT_DIST} au moment de la mesure")
    adj = []
    for u in (dv.get("units") or []):
        if not u.get("alive") or u.get("owner") == car.get("owner"):
            continue
        dd = _bfs(board, tile(car)).get(tile(u))
        if dd == 1:
            adj.append(u.get("visualId"))
    if with_blocker and not adj:
        pytest.fail("geometrie: aucun ennemi adjacent alors que le scenario en exige un")
    if not with_blocker and adj:
        pytest.fail(f"geometrie: ennemi(s) adjacent(s) inattendu(s) {adj} -- le gate serait ferme")

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

    # (5) MEME action OFFLINE, sur la MEME graine
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
            "plvl": plvl, "mult": mult, "adjacent_enemies": adj}


@pytest.fixture(scope="module")
def positif(rpc, build_runner):
    return _scenario(rpc, build_runner, with_blocker=False)


@pytest.fixture(scope="module")
def negatif_adjacent(rpc, build_runner):
    return _scenario(rpc, build_runner, with_blocker=True)


def test_instance_1213_est_materialisee_et_de_la_classe_portee(positif):
    """L'effet-riposte EXISTE offline et il est de la classe NATIVE mirroree -- sans quoi tout le
    reste mesurerait un `BaseEffect` anonyme."""
    inst = positif["inst"]
    assert inst is not None, "aucune instance 1213 materialisee sur le porteur"
    assert isinstance(getattr(inst, "impl", None) or inst,
                      (GrimRetributionCounterAttackEffect, type(inst)))
    assert GrimRetributionCounterAttackEffect.ACTIVATION_FREQUENCY == 1


def test_riposte_positif_replay_diff(positif):
    """Le TIREUR encaisse la riposte, et le port la rejoue AU MEME RANG DU FLUX RNG : les PV des
    DEUX unites coincident offline et live. C'est la garde forte -- une riposte absente, en trop, ou
    d'un montant different ferait diverger."""
    r = positif
    assert r["counter_amounts"], (
        "AUCUN degat sur le tireur cote LIVE : le natif n'a pas riposte, le montage est faux")
    for uid in (r["carrier"], r["shooter"]):
        assert r["off_hp"][uid] == r["live_hp"].get(uid), (
            f"replay-diff KO sur {uid}: offline {r['off_hp'][uid]} != live {r['live_hp'].get(uid)}")
    assert r["off_hp"][r["shooter"]] < r["hp_before"][r["shooter"]], (
        "le tireur n'a rien perdu cote OFFLINE : la riposte portee n'est pas partie")


def test_riposte_positif_attribution_dans_les_bornes(positif):
    """ATTRIBUTION : chaque montant de la riposte tombe dans `[minDmg, maxDmg]` du niveau PASSIF,
    multiplicateur de rarete applique. Sans cette garde, l'Overwatch de Sarquael -- qui frappe le
    MEME adversaire sur un AUTRE vecteur -- rendrait le test vert pour la mauvaise raison."""
    r = positif
    mn = ability_var(ABILITY, "minDmg", level=r["plvl"], multiplier_pct=r["mult"])
    mx = ability_var(ABILITY, "maxDmg", level=r["plvl"], multiplier_pct=r["mult"])
    assert mn and mx, "bornes de degat illisibles au gameconfig"
    # `nrOfHits = 1` : la riposte est UN coup. Les bornes sont larges (armure/pierce), on garde le
    # critere PLAFOND, qui est celui qui discrimine l'Overwatch (dont la base est l'arme, plus forte).
    assert all(0 < a <= mx for a in r["counter_amounts"]), (
        f"montants {r['counter_amounts']} hors bornes [1, {mx}] (min brut {mn})")


def test_armement_flag_isactive_tombe_apres_la_riposte(positif):
    """`& DeactivateEffect(effect)` de `$$CreateTargetTriggerBehaviour` : le flag
    `EffectComponent.IsActive @+0x5c` est VRAI avant, FAUX apres."""
    r = positif
    assert r["armed_before"] is not None, (
        "1213 ABSENT du canal includeInactive AVANT le coup -- l'effet n'est meme pas pose")
    assert r["active_before"] is True, (
        "l'instance n'etait pas ARMEE avant le coup -- la fenetre `NOT IsTurnOf(Owner)` "
        "(`On(0x12) -> ActivateEffect`) n'a pas joue")
    assert r["active_after"] is False, "le flag n'est pas retombe : le DeactivateEffect n'a pas joue"


def test_negatif_ennemi_adjacent_ferme_la_riposte(negatif_adjacent):
    """`NOT HasAdjacentEnemies(Owner, Tiles(Owner), false, false)` -- MEME tireur, MEME distance,
    MEME attaque : un seul ennemi au CONTACT de Sarquael suffit a fermer le gate.

    C'est la premiere phrase de l'i2 (<< if there is no enemy adjacent to Sarquael >>), et c'est le
    conjoint qu'aucune des deux soeurs de la famille ne porte."""
    r = negatif_adjacent
    assert r["adjacent_enemies"], "montage: le bloqueur n'est pas adjacent"
    assert not r["counter_amounts"], (
        f"le natif a riposte ({r['counter_amounts']}) alors qu'un ennemi est adjacent -- "
        "le gate `NOT HasAdjacentEnemies` ne serait pas celui qui est lu")
    for uid in (r["carrier"], r["shooter"]):
        assert r["off_hp"][uid] == r["live_hp"].get(uid), (
            f"replay-diff KO sur {uid}: offline {r['off_hp'][uid]} != live {r['live_hp'].get(uid)}")
    assert r["off_hp"][r["shooter"]] == r["hp_before"][r["shooter"]], (
        "le port a fait perdre des PV au tireur alors que le gate est FERME")
