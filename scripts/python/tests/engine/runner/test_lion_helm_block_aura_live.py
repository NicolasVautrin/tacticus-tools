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

# PREMISSE DE REGIME, RENDUE EXPLICITE (#933). Les discriminants ci-dessous lisent la stat
# TOTALE de block ; ils ne valent donc « contribution de l'aura » que si la BASE est nulle.
# Elle l'etait quand ce fichier a ete ecrit -- puis la bascule #419-r5/-r6 (items Best-In-Slot
# equipes PAR DEFAUT) a donne (36, 2349) de base a Azrael, ce qui rendait le fichier ROUGE en
# accusant `SurroundingFriends`. Le porteur « sans block » se CONSTRUIT desormais, il ne se
# suppose plus. Pas `TACTICUS_BIS_ITEMS=0`, qui deshabillerait tout le roster : cf. #914 §3.3.
_ZERO_BLOCK = "BlockChance=0,BlockDamage=0"
BUILD = ["--roster", "1", "--p-units", f"{CARRIER},{ALLY_DA},{ALLY_OTHER}", "--a-units", FOE,
         "--unit-stat", ";".join(f"{u}:{_ZERO_BLOCK}"
                                 for u in (CARRIER, ALLY_DA, ALLY_OTHER, FOE))]


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
    if not all(k in ids for k in (CARRIER, ALLY_DA, ALLY_OTHER, FOE)):
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


def test_base_de_block_nulle_le_levier_mord(lh_block):
    """PREMISSE DE MONTAGE : `--unit-stat …:BlockChance=0,BlockDamage=0` a bien MORDU.

    Le temoin est l'ENNEMI : `SurroundingFriends(Azrael)` ne peut par construction JAMAIS le
    selectionner, donc sa stat TOTALE de block EST sa base. S'il n'est pas a (0, 0), c'est le
    LEVIER qui a cesse de mordre -- et alors les discriminants ci-dessous ne mesurent plus la
    contribution de l'aura mais la base du roster, en accusant le selecteur. C'est exactement
    ce qui est arrive a ce fichier apres la bascule #419-r5/-r6.
    """
    seed = lh_block["steps"][0][1]
    foe = lh_block["ids"][FOE]
    assert seed[foe] == (0, 0), (
        f"base de block NON NULLE sur l'ennemi ({seed[foe]}) -> le levier --unit-stat "
        "BlockChance/BlockDamage ne mord plus ; les discriminants de ce fichier lisent la "
        "stat TOTALE et ne mesurent donc plus la contribution de l'aura LionHelm")


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
