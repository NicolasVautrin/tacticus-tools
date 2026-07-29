"""case-224 item 4 -- le predicat d'AURA `IsInContagionsOfNurgleRange` (`CursedPlagueBellAttackAbility`).

Le predicat natif est un NOEUD DSL :
    `IdunBattleLogic.Entities.DSLTriggers$$IsInUnitContagionsOfNurgleAura(Actor, Owner)`
    = `AmountIsGreater( ContagionsOfNurgleRange(Owner, 0, false), MinDistance(Actor, Owner) )`
et son etage de PORTEE (`IdunBattle.Entities.Triggers.AuraEffectRangeFormula$$Calculate` ->
`ContagionsOfNurgle_ArmorReduction_Effect` : `GetTrait` + `GetCurrentRange`) est PARTAGE, a l'identique,
avec `IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount` -- le moteur de la version d'EQUIPE,
que le natif EXPOSE live par `abilityTargets` (le `GetDynamicInvalidTargetReason` d'`EntropyCannons`).

Ces gardes confrontent donc :
  * OFFLINE  la table `GetRangeOnOwnerTurn` (1/2/3) et le cast `IAuraEffect` ;
  * LIVE     l'etage TRAIT + PORTEE + DISTANCE, par l'oracle `abilityTargets` -- le SEUIL de distance
             doit suivre `TurnsStarted(porteur)`, ce qui exerce la table en plusieurs points.

Le comparateur de la version UNITE est STRICT (`dist < range`) la ou celui de la version EQUIPE est
INCLUSIF (`dist <= range`) : ce n'est PAS une coquille, c'est l'overload `AmountIsGreaterAbilityTrigger
$$.ctor(amount, minAmount)` d'un cote contre le `if (r < d) continue` de l'autre (XREF + decompile).
Le test verrouille la relation `rayon UNITE == rayon EQUIPE - 1` pour qu'une future « harmonisation »
casse ici plutot qu'en silence.

Probe de mesure : `scripts/python/probe_224_contagions_aura_range.py`.
ASCII-only ; state-file UNIQUE sous `logs/` ; runner dispose en fin de test.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import hexgeo
from engine.runner.components import StatsComponent
from engine.runner.snapshot import load_state
from engine.entities.stats import StatType

AGENT_ID = "case224aura"
PYDIR = Path(__file__).resolve().parents[3]                        # scripts/python
ROOT = Path(__file__).resolve().parents[5]                         # racine repo
STATE = ROOT / "logs" / f"_pytest_{AGENT_ID}.json"

BOARD = "C1_02"
SEED = "4242"
ENTROPY = 1168                                     # ActiveAbilityType.EntropyCannons (deathCrawler)
AURA = 1071                                        # EffectType.ContagionsOfNurgle_ArmorReduction1
# `--advance 4` amene `TurnsStarted(porteur)` a 3 -> `GetRangeOnOwnerTurn(3) = 2`, le palier
# INTERMEDIAIRE : le seuil natif y vaut 2, donc d=1 ET d=2 sont dedans et d=3 dehors. C'est le
# regime le plus discriminant en UN seul montage (les deux branches + une transition de palier
# par rapport au seuil 1 du regime frais).
ADVANCE = 4
A_UNITS = "custoKyrus,astraBullgryn,ultraTitus"    # 3 ennemis TANKY : avec un seul, `--advance`
                                                   # termine la bataille et la MoW quitte decisionView


# ------------------------------------------------------------------ offline

def test_aura_effect_table_offline():
    """`ContagionsOfNurgle_ArmorReduction_Effect` : `GetTrait` / `GetMaxRange` / `GetRangeOnOwnerTurn`.
    La table est comparee a la transcription LITTERALE du corps compile de la surcharge statique
    `$$CalculateRange(roundsInGame)` : `if (2 < n) return (4 < n) + 2 ; return 1`."""
    from engine.entities.effects.aura import (aura_trait, aura_max_range, aura_current_range,
                                              aura_next_turn_range, aura_range_on_owner_turn,
                                              is_aura_effect)
    from engine.entities.traits.unit_trait import UnitTrait
    assert aura_trait(AURA) == int(UnitTrait.ContagionsOfNurgle) == 0x7EB
    assert aura_max_range(AURA) == 3
    for n in range(0, 12):
        native = (int(n > 4) + 2) if n > 2 else 1
        assert aura_range_on_owner_turn(n) == native, n
        assert aura_current_range(AURA, n) == native, n
        assert aura_next_turn_range(AURA, n) == aura_range_on_owner_turn(n + 1), n
    # Le cast `as IAuraEffect` ECHOUE hors du registre -> les deux consommateurs rendent 0.
    for other in (1065, 1244, 5, 17):
        assert not is_aura_effect(other)
        assert aura_trait(other) is None and aura_max_range(other) is None


def test_unit_predicate_is_strict_vs_team_inclusive_offline():
    """Le rayon EFFECTIF de la version UNITE vaut celui de la version EQUIPE MOINS UN, a tout palier.
    Verrou anti-« harmonisation » : `IsInUnitAura` utilise `AmountIsGreater` (STRICT) alors que
    `get_in_range_aura_amount` compte des que `d <= r` (INCLUSIF)."""
    from engine.entities.effects.aura import aura_range_on_owner_turn
    from engine.entities.triggers import IsInUnitAura
    from engine.entities.selectors import Caster, Target
    from engine.dsl.base import DslContext
    node = IsInUnitAura(Target(), AURA, Caster())
    for turns in range(0, 8):
        rng_ = aura_range_on_owner_turn(turns)
        for dist in range(0, 5):
            carrier = {"id": 1, "team": 1, "pos": {"col": 0, "row": 0}, "alive": True, "hp": 10}
            other = {"id": 2, "team": 2, "pos": {"col": dist, "row": 0}, "alive": True, "hp": 10}
            # colonne pure -> distance hex == |dcol| seulement pour dcol pair ; on cale la position
            # par recherche pour rester exact quel que soit le repere offset.
            got = None
            for c in range(-6, 7):
                for r in range(-6, 7):
                    if hexgeo.distance((0, 0), (c, r)) == dist:
                        got = (c, r)
                        break
                if got:
                    break
            other["pos"] = {"col": got[0], "row": got[1]}
            ctx = DslContext(units=[carrier, other], caster=carrier, target=other,
                             has_trait=lambda u, t: u["id"] == 1,
                             get_stat=lambda u, s, v=0, lv=None: turns if u["id"] == 1 else 0)
            assert node.should_trigger(ctx) is (dist < rng_), (turns, dist, rng_)


# ------------------------------------------------------------------ harnais live

def _rpc_factory(host, live_session):
    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r
    return _rpc


def _build() -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
         "--p-units", "deathTyphus,necroWarden", "--a-units", A_UNITS,
         "--p-mow", "deathCrawler", "--advance", str(ADVANCE), "--maxpump", "400",
         "--state-file", str(STATE)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        pytest.skip(f"build KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    return json.loads(STATE.read_text())["runnerId"]


def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dec, ob, snap, board=Board(bg["tiles"], adjacency="evenq"))
    return state, dec, ob, bg


def _targets(rpc, rid, caster, ability):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    if row is None:
        return []
    for a in (row.get("abilities") or []):
        return a.get("targets") or []
    return []


def _move(rpc, rid, uid, col, row):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 90)


def _turns_started(state, uid):
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    st = getattr(sc.ctx, "stats", None) if sc is not None else None
    return int(st.get_stat(int(StatType.TURNS_STARTED), 0)) if st is not None else None


def _port_team_verdict(state, mow_id, enemy_id) -> bool:
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.entities.triggers import IsInTeamAura
    from engine.entities.selectors import Caster, Target
    ctx = entities_from_state(state, caster_id=mow_id, target_id=enemy_id)
    return bool(IsInTeamAura(Target(), AURA, Caster()).should_trigger(ctx))


def _port_unit_verdict(state, carrier_id, enemy_id) -> bool:
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.runner.abilities.deathguard import is_in_contagions_of_nurgle_range
    ctx = entities_from_state(state, caster_id=carrier_id, target_id=enemy_id, actor_id=enemy_id)
    return bool(is_in_contagions_of_nurgle_range().should_trigger(ctx))


def _dispose(host, live_session, rid):
    try:
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:                                     # noqa: BLE001
        pass


# ------------------------------------------------------------------ live

def test_contagions_aura_range_live(host, live_session):
    """ORACLE = `abilityTargets(deathCrawler, EntropyCannons)`. Sur un runner sans modificateur
    negatif de `FixedArmor`, la 2e branche de `EntropyCannonsAbility$$GetDynamicInvalidTargetReason`
    est muette -> la legalite de la cible EST `IsInTeamContagionsOfNurgleAura(target, caster)`.

    On DEPLACE le porteur d'aura a distance 1, 2, 3, 4 de l'ennemi (drive-positions) et on exige
    l'accord natif/port a chaque distance, PLUS le fait que le SEUIL observe == `GetCurrentRange` du
    porteur : c'est ce qui distingue la table 1/2/3 d'un rayon constant."""
    rpc = _rpc_factory(host, live_session)
    rid = _build()
    try:
        state, dec, ob, bg = _load(rpc, rid)
        mow = next((m for m in (dec.get("mows") or []) if m.get("visualId") == "deathCrawler"), None)
        if mow is None:
            pytest.skip("MoW deathCrawler absente de decisionView (bataille terminee par --advance)")
        mow_id, team = mow["casterId"], mow["team"]
        carrier = next(u for u in ob["units"] if u["visualId"] == "deathTyphus")
        nocar = next(u for u in ob["units"] if u["visualId"] == "necroWarden")
        enemy = next(u for u in ob["units"] if u["teamId"] != team and not u.get("isDead"))
        ek = (enemy["col"], enemy["row"])
        tiles = bg["tiles"]

        from engine.entities.effects.aura import aura_range_on_owner_turn
        turns = _turns_started(state, carrier["squadId"])
        expected_range = aura_range_on_owner_turn(turns or 0)

        # DRIVE POSITIONS : le non-porteur d'abord ECARTE (il ne doit jamais decider), puis le
        # porteur promene aux distances 1..4 de l'ennemi.
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        far = [t for t in tiles if t.get("walkable", True)
               and (t["col"], t["row"]) not in occ
               and hexgeo.distance((t["col"], t["row"]), ek) >= 6]
        if far:
            _move(rpc, rid, nocar["squadId"], far[0]["col"], far[0]["row"])

        seen = 0
        for want in (1, 2, 3, 4):
            state, _dec, ob, _bg = _load(rpc, rid)
            cur = next(u for u in ob["units"] if u["squadId"] == carrier["squadId"])
            occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
            occ.discard((cur["col"], cur["row"]))
            cand = [t for t in tiles if t.get("walkable", True)
                    and (t["col"], t["row"]) not in occ
                    and hexgeo.distance((t["col"], t["row"]), ek) == want]
            if not cand:
                continue
            _move(rpc, rid, carrier["squadId"], cand[0]["col"], cand[0]["row"])
            state, _dec, ob, _bg = _load(rpc, rid)
            cur = next(u for u in ob["units"] if u["squadId"] == carrier["squadId"])
            dist = hexgeo.distance((cur["col"], cur["row"]), ek)
            native = any(t.get("targetId") == enemy["squadId"]
                         for t in _targets(rpc, rid, mow_id, ENTROPY))
            port = _port_team_verdict(state, mow_id, enemy["squadId"])
            assert native == port, (
                f"desaccord aura d={dist} turns={turns}: natif={native} port={port}")
            # le SEUIL natif observe DOIT etre `GetCurrentRange(porteur)` : c'est ce qui prouve la
            # table 1/2/3 plutot qu'un rayon constant.
            assert native == (dist <= expected_range), (
                f"seuil natif d={dist} = {native}, attendu {dist <= expected_range} "
                f"(GetCurrentRange({turns}) = {expected_range})")
            # version UNITE (STRICT) : rayon effectif = range - 1, sur la MEME scene.
            unit_v = _port_unit_verdict(state, carrier["squadId"], enemy["squadId"])
            assert unit_v == (dist < expected_range), (dist, expected_range, unit_v)
            seen += 1
        assert seen >= 3, f"trop peu de distances exercees ({seen})"

        # GATE TRAIT : porteur ECARTE, voisin ADJACENT sans le trait -> aucune aura des deux cotes.
        state, _dec, ob, _bg = _load(rpc, rid)
        cur = next(u for u in ob["units"] if u["squadId"] == carrier["squadId"])
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        occ.discard((cur["col"], cur["row"]))
        away = [t for t in tiles if t.get("walkable", True)
                and (t["col"], t["row"]) not in occ
                and hexgeo.distance((t["col"], t["row"]), ek) >= 6]
        if away:
            _move(rpc, rid, carrier["squadId"], away[0]["col"], away[0]["row"])
        state, _dec, ob, _bg = _load(rpc, rid)
        n2 = next(u for u in ob["units"] if u["squadId"] == nocar["squadId"])
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        occ.discard((n2["col"], n2["row"]))
        adj = [t for t in tiles if t.get("walkable", True)
               and (t["col"], t["row"]) not in occ
               and hexgeo.distance((t["col"], t["row"]), ek) == 1]
        if adj:
            _move(rpc, rid, nocar["squadId"], adj[0]["col"], adj[0]["row"])
            state, _dec, ob, _bg = _load(rpc, rid)
            native = any(t.get("targetId") == enemy["squadId"]
                         for t in _targets(rpc, rid, mow_id, ENTROPY))
            port = _port_team_verdict(state, mow_id, enemy["squadId"])
            assert native is False and port is False, (
                f"gate TRAIT : un voisin SANS ContagionsOfNurgle ne cree pas d'aura "
                f"(natif={native} port={port})")
    finally:
        _dispose(host, live_session, rid)
