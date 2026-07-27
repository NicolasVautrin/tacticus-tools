"""LionHelm (1163, darkaAzrael) — AURA stat-mod PROJETEE BlockDamage(1214)/BlockChance(1232) : offline == live.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LionHelmAbility$$CreateBehaviour` pose deux
`AddDynamicStatModifierEffect(targets = Owner)` sur AZRAEL ; leur `CreateTargetSelector` (vtable slot
+0x538) projette la `ValueModification` sur `SurroundingFriends(Azrael, ConfigConst(range) = 2)`, le
volet BlockChance ajoutant `UnitsFromFaction(UnitFaction.DarkAngels = 10)`.

TROIS discriminants dans un seul runner, dont un NEGATIF :
  * ami DARK ANGELS a <= 2 hexes  -> blockDamage ET blockChance
  * ami NON Dark Angels a <= 2    -> blockDamage SEUL (le gate faction MORD)
  * ami hors rayon                -> RIEN (cas NEGATIF)
  * Azrael lui-meme               -> RIEN (`SurroundingFriends` exclut la source)
Et la MOBILITE : le natif reverte/reapplique a chaque move (`UpdateEffectTargets`) — on l'exige aussi
du port (`runner/operations/aura_stat_mods.py`, appele par `MoveUnitOperation`).
"""
from __future__ import annotations

import pytest

CARRIER = "darkaAzrael"
ALLY_DA = "darkaHellblaster"      # ami DARK ANGELS
ALLY_OTHER = "ultraApothecary"    # ami NON Dark Angels
FOE = "necroOverlord"
BUILD = ["--roster", "1", "--p-units", f"{CARRIER},{ALLY_DA},{ALLY_OTHER}", "--a-units", FOE]


def _live_blocks(rpc, rid):
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    return {int(u["entityId"]): (int((u.get("stats") or {}).get("blockChance") or 0),
                                 int((u.get("stats") or {}).get("blockDamage") or 0))
            for u in (snap.get("units") or [])}


def _off_blocks(state):
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    out = {}
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None or sc.ctx is None:
            continue
        out[int(uid)] = (int(sc.ctx.stat(StatType.BLOCK_CHANCE)),
                         int(sc.ctx.stat(StatType.BLOCK_DAMAGE)))
    return out


@pytest.fixture(scope="module")
def lh_block(rpc, build_runner):
    """Monte le runner, charge l'etat offline, puis rejoue 3 deplacements EN LIVE ET OFFLINE."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import MoveUnitMessage

    rid = build_runner("4242", extra=BUILD)["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    ids = {u.get("visualId"): u["id"] for u in (dv.get("units") or []) if u.get("alive")}
    if not all(k in ids for k in (CARRIER, ALLY_DA, ALLY_OTHER)):
        pytest.skip(f"unite absente du build ({sorted(ids)})")
    state = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    runner = Runner(state).install_default_handlers(20)
    steps = []

    def snap_step(label):
        steps.append((label, _live_blocks(rpc, rid), _off_blocks(state)))

    def move(uid, col, row):
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 40)
        runner.apply(MoveUnitMessage(uid, (col, row)))

    snap_step("seed")
    move(ids[ALLY_DA], 5, 5)
    snap_step("da_out")
    move(ids[ALLY_OTHER], 4, 4)
    snap_step("other_out")
    move(ids[ALLY_DA], 1, 1)
    snap_step("da_back")
    return {"ids": ids, "steps": steps}


def test_block_aura_offline_equals_live_at_every_step(lh_block):
    """A CHAQUE etape (seed, sorties de rayon, retour), les stats de block offline == live."""
    for label, live, off in lh_block["steps"]:
        for uid in lh_block["ids"].values():
            assert live.get(uid) == off.get(uid), (
                f"[{label}] u{uid} : block offline {off.get(uid)} != live {live.get(uid)} "
                "(aura LionHelm mal materialisee / mal revertee)")


def test_block_aura_discriminants(lh_block):
    """Les gates du selecteur MORDENT : faction pour blockChance, rayon pour les deux, self exclu."""
    ids = lh_block["ids"]
    seed = dict(zip(("label", "live", "off"), lh_block["steps"][0]))["live"]
    da_out = dict(zip(("label", "live", "off"), lh_block["steps"][1]))["live"]
    az, da, other = ids[CARRIER], ids[ALLY_DA], ids[ALLY_OTHER]
    assert seed[da][0] > 0 and seed[da][1] > 0, (
        f"ami DARK ANGELS a portee sans bonus de block ({seed[da]})")
    assert seed[other][1] > 0, f"ami a portee sans blockDamage ({seed[other]})"
    assert seed[other][0] == 0, (
        f"ami NON Dark Angels a portee avec blockChance ({seed[other]}) -> "
        "le gate UnitsFromFaction(DarkAngels) ne mord pas")
    assert seed[az] == (0, 0), f"le PORTEUR se self-buffe ({seed[az]}) -> SurroundingFriends devrait l'exclure"
    assert da_out[da] == (0, 0), (
        f"ami hors rayon garde le bonus ({da_out[da]}) -> cas NEGATIF non respecte")
