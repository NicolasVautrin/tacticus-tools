"""PathOfCommand (1112, `eldarAutarch`) — AURA stat-mod PROJETEE **CRIT** (1107) : offline == live.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandAbility$$CreateBehaviour` pose DEUX
`AddDynamicStatModifierEffectToOwner` sur l'Autarch : `0x458 = 1112` sur `statType 0x0 = Attack`
(deja porte) et `0x453 = 1107` sur `statType 0x9 = CritChance` (#373). Le selecteur du volet CRIT
ajoute un noeud que le volet ATTACK n'a PAS :

    UnitsWithStatBiggerThan( SurroundingFriends(Owner, ConfigConst(range) = 2, unique,
                                                OnlyAliveAndTargetable),
                             CritChance, part Current, Constant(0), excludingEffect = true )

-> un allie A PORTEE dont la chance de crit est NULLE n'est PAS cible.

QUATRE discriminants, dont deux NEGATIFS :
  * allie a <= 2 hexes AVEC chance de crit  -> +extraCritChance
  * allie a <= 2 hexes SANS chance de crit  -> RIEN sur le crit, mais bien +extraDmg sur l'Attack
                                               (c'est ce qui prouve que c'est le GATE CRIT qui
                                               discrimine, et non la distance)
  * le porteur lui-meme                     -> RIEN (`SurroundingFriends` exclut la source)
  * allie sorti du rayon                    -> RIEN (revert), et RETOUR -> re-applique

Le hasard n'entre pas : on mesure la STAT `critChance` (`UnitExtensions$$GetStat`, deterministe),
jamais un jet de critique.

Deep-strike : l'Autarch arrive `TeleportStrike_TeleportingIn`, passives DEFERREES — le premier volet
confronte donc l'atterrissage lui-meme (live `endturn` vs `EndTurnOperation` offline).
Mesure de reference : `probe_373_path_of_command_extra_crit.py`.
"""
from __future__ import annotations

import pytest

CARRIER = "eldarAutarch"       # deep-strike + PathOfCommand
ALLY_CRIT = "eldarRanger"      # chance de crit forcee > 0 -> CIBLE du selecteur
ALLY_NOCRIT = "eldarFarseer"   # chance de crit 0 (la normalisation la met a 0) -> NON cible
FOE = "necroWarden"
CRIT_SEED = 20
BUILD = ["--p-units", f"{CARRIER},{ALLY_CRIT},{ALLY_NOCRIT}", "--a-units", FOE, "--no-ai",
         "--unit-stat", f"{ALLY_CRIT}:CritChance={CRIT_SEED}"]
EXTRA_CRIT = "PathOfCommand_ExtraCrit"


def _live(rpc, rid):
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    return {int(u["entityId"]): {
        "cc": int((u.get("stats") or {}).get("critChance") or 0),
        "d_cc": int((u.get("statDelta") or {}).get("critChance") or 0),
        "att": int((u.get("stats") or {}).get("attack") or 0),
        "d_att": int((u.get("statDelta") or {}).get("attack") or 0)}
        for u in (snap.get("units") or []) if u.get("entityId") is not None}


def _off(state):
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    out = {}
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None or sc.ctx is None:
            continue
        comp = sc.ctx.stats.components.get(int(StatType.CRIT_CHANCE))
        out[int(uid)] = {"cc": int(sc.ctx.stat(StatType.CRIT_CHANCE)),
                         "att": int(sc.ctx.stat(StatType.ATTACK)),
                         "per": dict(comp.modification.per_source) if comp is not None else {}}
    return out


def _attr(per) -> int:
    """Part de la modification CritChance attribuee a l'entite-effet 1107 (0 = restee opaque)."""
    return sum(v for k, v in per.items()
               if isinstance(k, tuple) and any(x == EXTRA_CRIT for x in k))


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


@pytest.fixture(scope="module")
def poc_crit(rpc, build_runner):
    """Monte le runner, confronte l'ATTERRISSAGE, puis rejoue une SORTIE/RETOUR de rayon en live
    ET offline. Un seul runner pour les quatre discriminants."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import OwnerComponent
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.operations.turnflow import EndTurnOperation
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state

    rid = build_runner("31337", extra=BUILD)["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    ids = {u.get("visualId"): u["id"] for u in (dv.get("units") or []) if u.get("alive")}
    if not all(k in ids for k in (CARRIER, ALLY_CRIT, ALLY_NOCRIT)):
        pytest.skip(f"unite absente du build ({sorted(ids)})")
    board = Board(bg["tiles"], adjacency="native_sym")
    s0 = load_state(dv, ob, snap, board=board)
    carrier, a_crit, a_flat = ids[CARRIER], ids[ALLY_CRIT], ids[ALLY_NOCRIT]
    if not s0.effects.has_effect(carrier, name="TeleportStrike_TeleportingIn"):
        pytest.skip("Autarch pas en teleport-in (deja pose ?)")
    d = {v: hexgeo.distance(_pos(s0, carrier), _pos(s0, v)) for v in (a_crit, a_flat)}
    if any(x is None or x > 2 for x in d.values()):
        pytest.skip(f"allies hors du rayon 2 au spawn ({d}) — montage non exercant")

    # --- ATTERRISSAGE : live `endturn` vs `EndTurnOperation` offline ---------------------
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30)
    land_live = _live(rpc, rid)
    s0.current_player_id = s0.get_entity(carrier).get_component(OwnerComponent).player
    EndTurnOperation.execute(s0, advance=False)
    land_off = _off(s0)

    # --- etat DEJA atterri, recapture : attribution + mobilite ---------------------------
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30)   # rends-moi la main
    dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
    sn1 = rpc("combatSnapshot", {"runnerId": rid}, 40)
    s1 = load_state(dv1, ob1, sn1, board=board)
    runner = Runner(s1).install_default_handlers(20)
    home = _pos(s1, a_crit)
    occupied = {_pos(s1, u) for u in s1.entities} - {home}
    # Tuiles LIBRES hors du rayon 2 du porteur, triees par proximite au point de depart de l'allie
    # (donc par plausibilite de budget de mouvement) — on ESSAIE jusqu'a ce que le natif accepte,
    # on ne subit pas la premiere venue. Foyer partage avec `probe_373_path_of_command_extra_crit`.
    from probe_373_path_of_command_extra_crit import out_of_ring_candidates
    cands = out_of_ring_candidates(board, _pos(s1, carrier), home, occupied)
    steps = [("seed", _live(rpc, rid), _off(s1))]
    out_tile = None
    for tile in cands[:12]:
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": a_crit, "to": {"col": tile[0], "row": tile[1]}}}, 40)
        if isinstance(res, dict) and res.get("ok") is False:
            continue                                   # hors budget de mouvement -> candidate suivante
        out_tile = tile
        break
    if out_tile is not None:
        runner.apply(MoveUnitMessage(a_crit, tuple(out_tile)))
        steps.append(("out", _live(rpc, rid), _off(s1)))
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": a_crit, "to": {"col": home[0], "row": home[1]}}}, 40)
        runner.apply(MoveUnitMessage(a_crit, tuple(home)))
        steps.append(("back", _live(rpc, rid), _off(s1)))
    return {"ids": ids, "carrier": carrier, "a_crit": a_crit, "a_flat": a_flat,
            "land": (land_live, land_off), "steps": steps, "out_tile": out_tile, "d": d}


def test_landing_crit_offline_equals_live(poc_crit):
    """L'atterrissage du deep-strike pose 1107 ET projette sa modification : offline == live."""
    live, off = poc_crit["land"]
    a_crit = poc_crit["a_crit"]
    assert live[a_crit]["d_cc"] > 0, (
        "le natif n'accorde AUCUN crit a l'allie apres l'atterrissage -- montage non exercant")
    for uid in (poc_crit["carrier"], a_crit, poc_crit["a_flat"]):
        assert off[uid]["cc"] == live[uid]["cc"], (
            f"u{uid} : critChance offline {off[uid]['cc']} != live {live[uid]['cc']} apres "
            "atterrissage (aura CRIT PathOfCommand non projetee a la pose de l'owner-effect)")


def test_crit_gate_bites_and_is_not_distance(poc_crit):
    """Le gate `UnitsWithStatBiggerThan(CritChance > 0)` MORD -- et c'est bien LUI, pas la distance :
    l'allie a crit 0 est a la MEME portee et recoit, lui, le +Attack du jumeau 1112."""
    live, off = poc_crit["land"]
    flat, crit, carrier = poc_crit["a_flat"], poc_crit["a_crit"], poc_crit["carrier"]
    assert poc_crit["d"][flat] <= 2, "l'allie CRIT=0 doit etre dans le rayon pour que le gate soit seul en cause"
    assert live[flat]["d_att"] > 0, (
        f"l'allie CRIT=0 ne recoit meme pas le +Attack de 1112 ({live[flat]['d_att']}) -> il est "
        "hors de l'aura, le gate CRIT n'est pas ce qui le distingue")
    assert live[flat]["d_cc"] == 0 and off[flat]["cc"] == 0, (
        f"allie a portee SANS chance de crit qui recoit du crit (live {live[flat]['d_cc']}, "
        f"port {off[flat]['cc']}) -> le noeud UnitsWithStatBiggerThan ne mord pas")
    assert live[crit]["d_cc"] > 0, "allie a portee AVEC chance de crit sans bonus -> selecteur trop strict"
    assert live[carrier]["d_cc"] == 0 and off[carrier]["cc"] == 0, (
        "le PORTEUR se self-buffe -> `SurroundingFriends` devrait l'exclure")


def test_crit_contribution_is_attributed_not_opaque(poc_crit):
    """La contribution est ATTRIBUEE a l'entite-effet (comme le natif, dont la source du ChangeStat
    EST l'entite-effet) et non laissee dans le residu opaque : c'est ce qui la rend RETIRABLE."""
    _, off = poc_crit["steps"][0][1], poc_crit["steps"][0][2]
    a_crit = poc_crit["a_crit"]
    assert _attr(off[a_crit]["per"]) > 0, (
        f"la modification CritChance de u{a_crit} n'est attribuee a aucun effet "
        f"({off[a_crit]['per']}) -> elle reste dans le residu opaque, donc IRRETIRABLE quand "
        "l'allie sort du rayon")


def test_crit_aura_offline_equals_live_at_every_step(poc_crit):
    """Sortie du rayon puis retour : le natif reverte/re-applique, le port doit suivre."""
    assert poc_crit["out_tile"] is not None, (
        "aucune tuile hors du rayon 2 ATTEIGNABLE par l'allie en un deplacement -> le cas NEGATIF "
        "(revert de l'aura) n'a PAS ete exerce ; rejouer sur un autre board (un skip ici serait "
        "un vert qui ment)")
    for label, live, off in poc_crit["steps"]:
        for uid in poc_crit["ids"].values():
            assert off[uid]["cc"] == live[uid]["cc"], (
                f"[{label}] u{uid} : critChance offline {off[uid]['cc']} != live {live[uid]['cc']} "
                "(aura CRIT PathOfCommand mal materialisee / mal revertee)")
    out_live = poc_crit["steps"][1][1][poc_crit["a_crit"]]
    assert out_live["d_cc"] == 0, (
        f"le natif garde le bonus de crit hors rayon (mod {out_live['d_cc']:+d}) -> la tuile de "
        "sortie n'est pas assez loin, le cas NEGATIF n'est pas exerce")
