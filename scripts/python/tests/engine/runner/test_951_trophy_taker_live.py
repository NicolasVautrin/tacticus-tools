"""#951 -- confrontation LIVE de `TrophyTaker` (`worldExecutions` << Tarvakh >>, passif 1229).

Le passif a TROIS faces, portees par DEUX artefacts natifs distincts, et chacune est confrontee
ici par REPLAY-DIFF RNG-seede (meme graine des deux cotes, meme action) :

 1. GATE FERME  -- cible au-dessus de `hpPct` : aucun bonus. C'est le TEMOIN, et il est
    indispensable : sans lui, un ecart de base se lirait comme un ecart du passif.
 2. GATE OUVERT -- cible SOUS `hpPct` : `+extraDmg` sur le coup. Le DIFFERENTIEL entre les deux
    regimes DOIT valoir exactement `ConfigVar(extraDmg)` au niveau/multiplicateur du porteur.
 3. APRES UN KILL -- le stat-mod `TrophyTaker_ExtraCritChance` (1288, `StatType.CriticalChance`)
    que le natif RE-ECRIT sur `On(UnitDefeated)`. Confronte SUR SA VALEUR, pas sur sa presence.

⚠ Le degat se lit dans les EVENTS de l'action, jamais dans les PV d'apres coup : `applyAction`
cloture le tour du porteur, le tour adverse s'ouvre, et un `necroWarden` (`LivingMetal`) REGENERE
-- mesure faite, ses PV MONTENT de 80000 a 93290 apres l'attaque. Comparer des PV d'apres coup
melangerait degat et regeneration.

⚠ Les trois regimes sont montes SANS KILL PREALABLE (sauf le troisieme, qui EST le kill). Ce n'est
pas une commodite : avec un kill avant la mesure, l'ecart natif/port est de 682 a 881 points, et il
NE VIENT PAS de ce passif -- `BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee`
(un AUTRE passif du meme porteur) indexe sa magnitude sur le compteur de victimes, que la CAPTURE
NE PUBLIE PAS. Residu #951-r3. La contre-epreuve est dans le fichier : sans kill, l'ecart est 0.

Geometrie CALCULEE et ASSERTIONNEE (`pytest.fail`, jamais un skip). ASCII only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

import gameconfig as GC
from engine.entities.effect_type import EffectType
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent, UnitComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test LIVE.
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
        # PROPRE A CE FICHIER : la chaine complete du passif 1229.
        "scripts/python/engine/entities/effects/loki/trophy_taker.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/loki/trophy_taker.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/dsl/base.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Test LIVE : il monte trois runners, pilote les positions par RPC et confronte le "
              "port au natif par REPLAY-DIFF RNG-seede. Le perimetre couvre la chaine du passif "
              "1229 (ses deux faces), l'etage `UnitsDefeatedBy` et le harnais de montage -- pas "
              "au-dela.",
}

CARRIER = "worldExecutions"      # Tarvakh -- HERO au pool, porteur de `TrophyTaker`
CIBLE = "necroWarden"            # cible d'OBSERVATION : PV forces, entamee ou non selon le regime
VICTIME = "orksNob"              # victime a tuer : 1 PV, unite NORMALE (ni Object ni Steppable)
ABILITY = "TrophyTaker"
EXTRA_CRIT_CHANCE = int(EffectType.TrophyTaker_ExtraCritChance)     # 0x508 = 1288
EXTRA_CRIT_DAMAGE = int(EffectType.TrophyTaker_ExtraCritDamage)     # 0x509 = 1289
PV_MAX = 200000
PV_SOUS = 20000                  # 10 %  -> SOUS `hpPct` = 50
PV_AU_DESSUS = 180000            # 90 %  -> AU-DESSUS


def _bfs(board, src):
    dist, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _tile(board, u):
    p = u.get("pos") or {}
    return board.id_at(p.get("col"), p.get("row"))


def _drive(rpc, rid, board, mover_vis, anchor_vis, want, side, tours=30):
    for _ in range(tours):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        mv, an = _alive(dv, mover_vis), _alive(dv, anchor_vis)
        if mv is None or an is None:
            return None
        dist = _bfs(board, _tile(board, an))
        if dist.get(_tile(board, mv)) == want:
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
    return _bfs(board, _tile(board, an)).get(_tile(board, mv))


def _monter(rpc, build_runner, pv_restants):
    b = build_runner("4321", extra=[
        "--roster", "1", "--p-units", CARRIER, "--a-units", "%s,%s" % (CIBLE, VICTIME),
        "--hp-player", "999999", "--crit", "0,0", "--crit-target", "0,0",
        "--block-target", "0,0", "--block-player", "0,0",
        "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (CIBLE, PV_MAX, pv_restants),
        "--unit-stat", "%s:Health=1,RemainingHealth=1" % VICTIME])
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        pytest.fail("boardGraph indisponible -- AUCUNE mesure n'a eu lieu")
    return rid, Board(bg["tiles"], adjacency="native_sym")


def _amener_et_frapper(rpc, rid, board, cible_vis):
    """Amene le porteur au CONTACT de `cible_vis`, prend la capture, joue le coup LIVE puis le MEME
    coup OFFLINE sur la MEME graine. Rend les deux mesures et le contexte du gate."""
    got = _drive(rpc, rid, board, CARRIER, cible_vis, 1, "friendly")
    if got != 1:
        pytest.fail("pilotage: porteur/%s = %s != 1" % (cible_vis, got))
    for _ in range(4):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        car = _alive(dv, CARRIER)
        if car is not None and dv.get("currentPlayer") == car.get("owner"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    car, cib = _alive(dv, CARRIER), _alive(dv, cible_vis)
    if car is None or cib is None:
        pytest.fail("unite manquante au moment de la mesure -- AUCUNE mesure n'a eu lieu")
    # GEOMETRIE ASSERTIONNEE, pas esperee.
    d = _bfs(board, _tile(board, car)).get(_tile(board, cib))
    if d != 1:
        pytest.fail("geometrie: porteur/%s = %s != 1 au moment de la mesure" % (cible_vis, d))
    norm = next((x for x in (car.get("abilities") or []) if x.get("kind") == "normal"), None)
    if norm is None:
        pytest.fail("pas d'attaque normale sur le porteur")

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dv, ob, snap, board=board)
    hc = state.get_entity(cib["id"]).get_component(HealthComponent)
    if hc is None or hc.hp is None or not hc.hp_max:
        pytest.fail("PV de la cible NON MESURES -- le gate serait indecidable")
    pct = 100.0 * hc.hp / hc.hp_max
    uc = next((u.get("unitConfig") or {} for u in (snap.get("units") or [])
               if u.get("entityId") == car["id"]), {})
    # Le PORT doit avoir vu ZERO victime : c'est ce qui rend l'ecart imputable au SEUL passif
    # mesure (cf. l'avertissement en tete de fichier).
    puc = state.get_entity(car["id"]).get_component(UnitComponent)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("ok")):
        pytest.fail("dumpRng KO -- pas de replay possible")
    rng = IntBasedMersenneTwister()
    rng.mt = list(s0["mt"])
    rng.mti = s0["mti"]
    state.rng = rng
    runner = Runner(state).install_default_handlers(20)
    hp_avant = hc.hp

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": car["id"], "targetId": cib["id"],
        "abilityType": norm["id"]}}, 90)
    if not (isinstance(res, dict) and res.get("ok")):
        pytest.fail("attaque live KO: %s" % str(res)[:200])
    a0 = (res.get("actions") or [{}])[0]
    coups = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == cib["id"] and "Amount" in td:
            coups.append(int(td["Amount"]))
    runner.apply(AttackUnitMessage(car["id"], cib["id"]))
    hc2 = state.get_entity(cib["id"]).get_component(HealthComponent)
    return {"carrier": car["id"], "cible": cib["id"], "pct": pct,
            "natif": sum(coups), "coups": coups,
            "port": (hp_avant - hc2.hp) if hc2.hp is not None else None,
            "victimes_port": len(puc.defeated_units) if puc is not None else None,
            "plvl": uc.get("passiveAbilityLevel"),
            "mult": uc.get("abilityVariablesMultiplier") or 100}


@pytest.fixture(scope="module")
def ferme(rpc, build_runner):
    rid, board = _monter(rpc, build_runner, PV_AU_DESSUS)
    return _amener_et_frapper(rpc, rid, board, CIBLE)


@pytest.fixture(scope="module")
def ouvert(rpc, build_runner):
    rid, board = _monter(rpc, build_runner, PV_SOUS)
    return _amener_et_frapper(rpc, rid, board, CIBLE)


@pytest.fixture(scope="module")
def apres_kill(rpc, build_runner):
    """REGIME 3 : le porteur tue une unite NORMALE. La capture est prise AVANT le coup, et le kill
    est rejoue OFFLINE sur la meme graine -- c'est le seul point ou le port peut recalculer le
    stat-mod (apres, le compteur natif a avance et la capture ne le publie pas)."""
    rid, board = _monter(rpc, build_runner, PV_AU_DESSUS)
    got = _drive(rpc, rid, board, CARRIER, VICTIME, 1, "friendly")
    if got != 1:
        pytest.fail("pilotage: porteur/victime = %s != 1" % got)
    for _ in range(4):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        car = _alive(dv, CARRIER)
        if car is not None and dv.get("currentPlayer") == car.get("owner"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    car, vic = _alive(dv, CARRIER), _alive(dv, VICTIME)
    if car is None or vic is None:
        pytest.fail("unite manquante avant le kill -- AUCUNE mesure n'a eu lieu")
    d = _bfs(board, _tile(board, car)).get(_tile(board, vic))
    if d != 1:
        pytest.fail("geometrie: porteur/victime = %s != 1" % d)
    norm = next((x for x in (car.get("abilities") or []) if x.get("kind") == "normal"), None)
    if norm is None:
        pytest.fail("pas d'attaque normale sur le porteur")

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dv, ob, snap, board=board)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("ok")):
        pytest.fail("dumpRng KO -- pas de replay possible")
    rng = IntBasedMersenneTwister()
    rng.mt = list(s0["mt"])
    rng.mti = s0["mti"]
    state.rng = rng
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(car["id"], vic["id"]))
    puc = state.get_entity(car["id"]).get_component(UnitComponent)
    port_mods = [(e.effect_type, getattr(e, "value", None))
                 for e in (state.effects.by_unit.get(car["id"]) or [])
                 if e.effect_type == EXTRA_CRIT_CHANCE]

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": car["id"], "targetId": vic["id"],
        "abilityType": norm["id"]}}, 90)
    if not (isinstance(res, dict) and res.get("ok")):
        pytest.fail("kill live KO: %s" % str(res)[:200])
    dvi = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                               "includeInactive": True}, 90)
    row = next((u for u in (dvi.get("units") or []) if u.get("id") == car["id"]), None)
    nat = next((e for e in ((row or {}).get("effects") or [])
                if e.get("effectType") == EXTRA_CRIT_CHANCE), None)
    vic2 = next((u for u in (dvi.get("units") or []) if u.get("visualId") == VICTIME), None)
    uc = next((u.get("unitConfig") or {} for u in (snap.get("units") or [])
               if u.get("entityId") == car["id"]), {})
    # #951-r1 : le couple `inMelee`, sur les DEUX faces et dans les DEUX regimes. Ce kill est un
    # corps-a-corps (le montage a impose `d == 1` plus haut), donc `Melee(1)` est attendu.
    vuc = state.get_entity(vic["id"]).get_component(UnitComponent)
    return {"carrier": car["id"], "victime_morte": bool(vic2 is not None and not vic2.get("alive")),
            "natif": nat, "port_mods": port_mods,
            "victimes_port": len(puc.defeated_units) if puc is not None else None,
            "plvl": uc.get("passiveAbilityLevel"),
            "mult": uc.get("abilityVariablesMultiplier") or 100,
            # face SIMULATION (le rejeu offline ci-dessus)
            "port_defeated_by_melee": (vuc.defeated_by_melee if vuc is not None else None),
            "port_melee": list(puc.defeated_units_melee) if puc is not None else None,
            "port_other": list(puc.defeated_units_other) if puc is not None else None,
            "victime_id": vic["id"],
            # face NATIVE (le meme kill, joue LIVE juste apres)
            "natif_defeated_by_melee": (None if vic2 is None else vic2.get("defeatedByMelee"))}


# ==================================================================================================
# [1] Le montage a bien atteint les regimes visés
# ==================================================================================================

def test_les_deux_regimes_encadrent_le_seuil(ferme, ouvert):
    seuil = int(GC.ability(ABILITY)["constants"]["hpPct"])
    assert ferme["pct"] >= seuil, "le regime TEMOIN doit etre AU-DESSUS du seuil"
    assert ouvert["pct"] < seuil, "le regime OUVERT doit etre SOUS le seuil"
    # Sans cette garde, un ecart mesure serait imputable au compteur de victimes d'un AUTRE passif
    # du meme porteur (`BlessingsOfKhorne`, residu #951-r3), pas a `TrophyTaker`.
    assert ferme["victimes_port"] == 0 and ouvert["victimes_port"] == 0


# ==================================================================================================
# [2] REPLAY-DIFF : le port est bit-exact dans LES DEUX regimes
# ==================================================================================================

def test_gate_ferme_bit_exact(ferme):
    """Cible AU-DESSUS de `hpPct` : le gate est ferme des DEUX cotes. Tout ecart ici serait
    PREEXISTANT au passif -- c'est la seule facon de rendre le regime ouvert interpretable."""
    assert ferme["natif"] > 0, "aucun degat natif : le regime est DEGENERE, il ne prouve rien"
    assert ferme["port"] == ferme["natif"]


def test_gate_ouvert_bit_exact(ouvert):
    """Cible SOUS `hpPct` : le bonus `extraDmg` s'applique, et le port doit rendre le MEME total."""
    assert ouvert["natif"] > 0
    assert ouvert["port"] == ouvert["natif"]


def test_le_differentiel_vaut_exactement_extra_dmg(ferme, ouvert):
    """`ForAddition(<gate>, ConfigVar(extraDmg))` : le differentiel entre les deux regimes est la
    SEULE grandeur qui isole le passif. Il doit valoir `extraDmg[niveau] x multiplicateur`, et
    `extraDmg` EST dans `variablesAffectedByRarityBonus`."""
    attendu = ability_var(ABILITY, "extraDmg", ferme["plvl"], multiplier_pct=ferme["mult"])
    assert attendu, "magnitude de config introuvable -- la mesure serait DEGENEREE"
    assert ouvert["natif"] - ferme["natif"] == int(attendu)
    assert ouvert["port"] - ferme["port"] == int(attendu)


# ==================================================================================================
# [3] Le stat-mod de chance de critique -- SUR SA VALEUR
# ==================================================================================================

def test_le_kill_a_eu_lieu(apres_kill):
    assert apres_kill["victime_morte"], "sans mort, le regime 3 ne mesure RIEN"
    assert apres_kill["victimes_port"] == 1, "le port n'a pas inscrit la victime au compteur"


def test_stat_mod_crit_chance_natif_et_port_concordent(apres_kill):
    """`AddOrUpdateStaticStatModifierEffect(Owner, 0x508, CriticalChance, Multiply(ConfigVar(
    extraCritChance), Count(NormalUnits(UnitsDefeatedBy(Owner)))), turns: null, isHidden: false)`.

    Confronte SUR LA VALEUR : une garde de PRESENCE serait verte avec un multiplicateur faux."""
    nat = apres_kill["natif"]
    assert nat is not None, "le natif n'a pose AUCUN stat-mod 1288 -- le regime est degenere"
    sm = nat.get("statMod") or {}
    attendu = ability_var(ABILITY, "extraCritChance", apres_kill["plvl"],
                          multiplier_pct=apres_kill["mult"])
    assert int(sm.get("StatType")) == 9                      # StatType.CriticalChance
    assert int(sm.get("Amount")) == int(attendu)             # 1 victime -> `extraCritChance x 1`
    assert int(sm.get("IsDynamic")) == 0                     # `AddStaticStatModifierEffect`
    assert int(sm.get("IsHidden")) == 0                      # `isHidden: false`, LU aux octets
    assert int(nat.get("remaining") or 0) == 0               # `turns: null` -> PERMANENT
    assert apres_kill["port_mods"] == [(EXTRA_CRIT_CHANCE, int(attendu))]


def test_951r1_in_melee_concorde_avec_le_natif(apres_kill):
    """#951-r1 -- LA CONFRONTATION DE LA FACE SIMULATION, sur le SEUL canal qui la publie.

    `IdunBattle.Operations.KillUnitOperation$$Execute` calcule
    `inMelee = rangeType.HasValue && rangeType.GetValueOrDefault() == Melee(1)` et l'ecrit DEUX
    fois : sur la VICTIME (`UnitComponent+0x178 = DefeatedByMeleeAttack`, publie par
    `readUnitDeathMeta` sous `decisionView.units[].defeatedByMelee`) et sur le TUEUR
    (`RegisterDefeatedUnit`, qui partitionne `@+0xa8` melee / `@+0xb0` autres).

    Le port ne tenait AUCUNE des deux en simulation (`in_melee` non passe, residu #951-r1 ferme par
    le port du slot 4 `BattleQuery$$GetAttackRangeType`). Ce montage est un corps-a-corps (`d == 1`
    impose par la fixture), donc le regime N'EST PAS degenere : `Melee` est attendu, et un port qui
    passerait `None` tomberait dans l'autre liste.

    Les deux faces sont confrontees SEPAREMENT -- ecrire l'une sans l'autre laisserait
    `PossessionAbility` (qui lit la victime) et `TrophyTakerAbility` (qui lit le tueur) en desaccord
    sur la MEME mort."""
    assert apres_kill["victime_morte"], "sans mort, rien n'est mesure"
    nat = apres_kill["natif_defeated_by_melee"]
    assert nat is not None, (
        "`decisionView.units[].defeatedByMelee` absent du canal -- l'oracle natif n'existe plus, "
        "cette confrontation ne prouverait rien")
    assert bool(nat) is True, (
        "le natif ne classe PAS ce kill en melee alors que le montage impose `d == 1` : le regime "
        "est degenere, l'assertion de concordance ci-dessous serait vraie pour la mauvaise raison")
    assert apres_kill["port_defeated_by_melee"] is bool(nat), (
        "face VICTIME : port=%r natif=%r" % (apres_kill["port_defeated_by_melee"], nat))
    assert apres_kill["port_melee"] == [apres_kill["victime_id"]], (
        "face TUEUR : la victime d'un kill de MELEE doit entrer dans `@+0xa8`, pas dans `@+0xb0` "
        "-- melee=%r autres=%r" % (apres_kill["port_melee"], apres_kill["port_other"]))
    assert apres_kill["port_other"] == [], (
        "la victime est inscrite DEUX fois, ou dans la mauvaise liste : %r" % (apres_kill["port_other"],))


def test_extra_crit_chance_nest_pas_rarity_scale(apres_kill):
    """`variablesAffectedByRarityBonus == ["extraDmg", "extraCritDmg"]` -- l'ASYMETRIE entre les
    trois variables du meme passif. Contre-epreuve : si `extraCritChance` etait scale, la valeur
    attendue changerait avec le multiplicateur, et le stat-mod natif ne la porterait plus."""
    cfg = GC.ability(ABILITY)
    assert "extraCritChance" not in cfg["variablesAffectedByRarityBonus"]
    brut = cfg["variables"]["extraCritChance"][int(apres_kill["plvl"]) - 1]
    sm = (apres_kill["natif"] or {}).get("statMod") or {}
    assert int(sm.get("Amount")) == int(brut), \
        "le natif porte la valeur BRUTE : le multiplicateur de rarete ne s'y applique pas"
