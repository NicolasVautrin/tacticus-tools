"""GARDE des 3 actives Necrons portees par #116 (`case-116-necrons-lot1.md`) :
ResurrectionOrb (1009), MultiThreatEliminator (1006), Chronometron (1226).

Le PROBE (`probe_116_necrons.py`) MESURE (confront live complet, 4 regimes MTE, 4 rounds Orb) ; ces
tests GARDENT les invariants STRUCTURELS que le port ne doit plus jamais perdre, en interrogeant un
ORACLE (gameconfig / decompile), jamais un scalaire fige :

  * 1009 : le nb de summons == `Min(Count(amis LivingMetal morts) + TURNS_STARTED(caster), 6)` BRIDE par
    le nb d'hexes libres adjacents (`CanAddUnit(AdjacentTiles(caster))`) ; l'unite spawnee est celle de
    `constants.unitId` ; AUCUN revive (le set des unites MORTES est inchange).
  * 1006 : la chaine ne repart QUE si la cible MEURT, avec `max(0, H - k - 1) + extraHit` coups
    (loi #125, H = coups appliques, k = index du coup fatal) ; sans kill elle a exactement UN maillon.
  * 1226 : `Foreach(SurroundingEnemies(caster, range))` -> Pinned|Stunned + Chronometron_ExtraDamage sur
    CHAQUE ennemi du disque et sur AUCUN allie/le caster ; la branche `HasTrait(It, Summon)` route vers
    Stunned.

Etat live REEL (board + stats + rng du runner), cast par le CHEMIN REEL
(`AbilityHandler.visit_ActiveAbilityMessage`). ASCII only.
"""
from __future__ import annotations

import pytest

import gameconfig as GC
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.handler import ABILITY_CLASSES, AbilityHandler
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state
from engine.entities.stats import StatType

RESURRECTION_ORB, CHRONOMETRON, MULTI_THREAT = 1009, 1226, 1006


def _mk(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def mkstate():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
            st.rng = rng
        return st
    return mkstate, board


def _cast(state, caster, target, ability):
    h = AbilityHandler(state)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(caster_id=int(caster),
                                                      target_id=None if target is None else int(target),
                                                      ability_type=int(ability)))
    return h.last or {}


def _by_visual(state, visual):
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == visual and uc.alive:
            return eid
    return None


def _place(state, uid, col, row):
    pc = state.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = col, row


def _free_adjacent(state, board, uid):
    """`CanAddUnit(AdjacentTiles(u))` : hexes voisins WALKABLE et LIBRES (occupant vivant)."""
    pc = state.get_entity(uid).get_component(PositionComponent)
    occ = set()
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        p = e.get_component(PositionComponent)
        if p is not None and (uc is None or uc.alive):
            occ.add(board.id_at(p.col, p.row))
    return [t for t in board.neighbours(board.id_at(pc.col, pc.row))
            if t not in occ and board.walkable(t)]


def _dead_ids(state):
    return {eid for eid, e in state.entities.items()
            if e.get_component(UnitComponent) is not None
            and not e.get_component(UnitComponent).alive}


# ------------------------------------------------------------------ 1009 ResurrectionOrb

def test_resurrection_orb_registered_and_summon_count_live(rpc, build_runner):
    """Le nb de summons = min(FORMULE, hexes libres) et l'unite spawnee est `constants.unitId`.
    ORACLE : la formule native `Min(Count(amis LivingMetal morts) + StatAmount(caster, TURNS_STARTED), 6)`
    recalculee ICI depuis l'ECS + `gameconfig`, JAMAIS un scalaire fige."""
    assert ABILITY_CLASSES.get(RESURRECTION_ORB) is not None, "1009 doit etre dans ABILITY_CLASSES"
    rid = build_runner("777", extra=["--p-units", "necroOverlord,necroDestroyer",
                                     "--a-units", "eldarRanger,astraBullgryn", "--no-ai"])["rid"]
    mkstate, board = _mk(rpc, rid)
    st = mkstate()
    cid = _by_visual(st, "necroOverlord")
    if cid is None:
        pytest.skip("necroOverlord absent du runner")
    sc = st.get_entity(cid).get_component(StatsComponent)
    oc = st.get_entity(cid).get_component(OwnerComponent)
    turns = int(sc.ctx.stats.get_stat(int(StatType.TURNS_STARTED), 0) or 0)
    dead_livingmetal = 0
    for eid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        eoc = e.get_component(OwnerComponent)
        esc = e.get_component(StatsComponent)
        if uc is None or eoc is None or esc is None or uc.alive:
            continue
        if eoc.team == oc.team and "LivingMetal" in (getattr(esc.ctx, "traits", None) or ()):
            dead_livingmetal += 1
    formula = min(dead_livingmetal + turns, 6)                 # GetMaxSummonsFormula
    free = len(_free_adjacent(st, board, cid))                 # CanAddUnit(AdjacentTiles(caster))
    dead_before = _dead_ids(st)

    diag = _cast(st, cid, cid, RESURRECTION_ORB)               # SELF-cast (TargetingOptions natives)
    assert diag.get("ported") is True
    assert diag["count"] == formula, (diag["count"], formula, turns, dead_livingmetal)
    assert len(diag["spawned"]) == min(formula, free), (diag["spawned"], formula, free)
    # SUMMON PUR : l'arbre natif ne contient NI Revive NI Resurrect -> aucun mort ne revient.
    assert _dead_ids(st) >= dead_before, "ResurrectionOrb ne ressuscite RIEN (summon pur)"
    # `unitId` = `GetStringConstant(config, 0)`. CONVENTION PARTAGEE de la feuille `Spawn` (tous les
    # ports de summon) : l'entite offline porte l'ID GAMECONFIG (`necroSmnWarrior`) ; LIVE le summon
    # apparait sous le `visualId` de son entree gameconfig (`necroNpc1Warrior`) — piege de nommage
    # deja documente (case-92 §5), commun a TOUS les Spawn, pas specifique a 1009.
    vid = (GC.ability("ResurrectionOrb") or {}).get("constants", {}).get("unitId")
    for sid_ in diag["spawned"]:
        uc = st.get_entity(sid_).get_component(UnitComponent)
        assert uc.visual_id == vid, (uc.visual_id, vid)
        assert st.get_entity(sid_).get_component(HealthComponent).hp > 0


# ------------------------------------------------------------------ 1006 MultiThreatEliminator

def test_multi_threat_chain_only_on_kill_live(rpc, build_runner):
    """La chaine ne repart QUE si la cible MEURT. Trois regimes sur le MEME etat (une seule variable :
    les PV de la cible) : cible pleine -> UN maillon ; cible ramenee sous le total du 1er volet ->
    DEUX maillons ; cible a 1 PV -> report STRICTEMENT plus grand (coup fatal plus precoce). Le report
    est confronte a la loi `max(0, H - k - 1) + extraHit` (#125), pas a un scalaire."""
    assert ABILITY_CLASSES.get(MULTI_THREAT) is not None, "1006 doit etre dans ABILITY_CLASSES"
    rid = build_runner("4242", extra=["--p-units", "necroDestroyer",
                                      "--a-units", "eldarRanger,astraBullgryn", "--no-ai",
                                      "--crit", "0,0"])["rid"]
    mkstate, board = _mk(rpc, rid)

    def scene(hp_target):
        st = mkstate()
        cid = _by_visual(st, "necroDestroyer")
        foes = [eid for eid, e in st.entities.items()
                if e.get_component(OwnerComponent) is not None
                and e.get_component(OwnerComponent).team
                != st.get_entity(cid).get_component(OwnerComponent).team
                and e.get_component(UnitComponent).alive]
        assert len(foes) >= 2, foes
        cp = st.get_entity(cid).get_component(PositionComponent)
        # DRIVE des positions : la cible a portee 1 du caster, le 2e ennemi ADJACENT a la cible
        # (le selecteur de cible suivante = disque range du caster INTER voisins de la derniere cible).
        ring = board.neighbours(board.id_at(cp.col, cp.row))
        t0 = board.by_id[ring[0]]
        _place(st, foes[0], t0["col"], t0["row"])
        nb = [t for t in board.neighbours(ring[0]) if t != board.id_at(cp.col, cp.row)]
        t1 = board.by_id[nb[0]]
        _place(st, foes[1], t1["col"], t1["row"])
        for f in foes:
            hc = st.get_entity(f).get_component(HealthComponent)
            hc.hp = int(hp_target)
        return st, cid, foes

    # (a) cible TANKY -> aucun kill -> chaine d'UN maillon, le 2e ennemi INTACT
    st, cid, foes = scene(200000)
    hp2 = st.get_entity(foes[1]).get_component(HealthComponent).hp
    diag = _cast(st, cid, foes[0], MULTI_THREAT)
    assert diag.get("ported") is True
    assert len(diag["chain"]) == 1, diag["chain"]
    assert diag["chain"][0]["hits"] == 6, diag["chain"][0]     # champ statique de la classe native
    assert st.get_entity(foes[1]).get_component(HealthComponent).hp == hp2

    # (b) cible FRAGILE -> kill -> le 2e maillon recoit `max(0, H - k - 1) + extraHit` coups
    # (H = coups appliques, k = index 1-based du coup fatal). ORACLE = la loi #125 recalculee ICI
    # depuis la part PV par coup du 1er maillon, JAMAIS un scalaire fige : l'ancienne assertion
    # `1 + extraHit` (#116) etait calibree sur un seul regime et passait par coincidence.
    extra = int(GC.ability("MultiThreatEliminator")["constants"]["extraHit"])
    dmg1 = diag["chain"][0]["total"]

    def report(diag_):
        c0 = diag_["chain"][0]
        per, hp = list(c0["per_hit_health"]), int(c0["hp_before"])
        acc = 0
        for i, h in enumerate(per):
            acc += int(h)
            if acc >= hp:
                return max(0, len(per) - (i + 1) - 1) + extra
        return 0

    st, cid, foes = scene(max(1, dmg1 // 2))
    diag2 = _cast(st, cid, foes[0], MULTI_THREAT)
    assert len(diag2["chain"]) >= 2, diag2["chain"]
    assert diag2["chain"][1]["hits"] == report(diag2), (diag2["chain"], extra)
    assert diag2["chain"][1]["target"] == foes[1]
    assert not st.get_entity(foes[0]).get_component(UnitComponent).alive

    # (c) MEME scene, cible ENCORE plus fragile -> le coup fatal arrive PLUS TOT -> report PLUS GRAND.
    # C'est ce contre-cas qui interdit a un report CONSTANT de passer le test.
    st3, cid3, foes3 = scene(1)
    diag3 = _cast(st3, cid3, foes3[0], MULTI_THREAT)
    assert len(diag3["chain"]) >= 2, diag3["chain"]
    assert diag3["chain"][1]["hits"] == report(diag3), (diag3["chain"], extra)
    assert diag3["chain"][1]["hits"] > diag2["chain"][1]["hits"], (
        f"mesure NON discriminante : meme report ({diag3['chain'][1]['hits']}) pour un coup fatal "
        f"plus precoce -- un report CONSTANT passerait")


# ------------------------------------------------------------------ 1226 Chronometron

def test_chronometron_poses_effects_on_surrounding_enemies_live(rpc, build_runner):
    """`Foreach(SurroundingEnemies(caster, range))` : Pinned + Chronometron_ExtraDamage sur CHAQUE ennemi
    du disque, sur AUCUN allie ni sur le caster ; branche `HasTrait(It, Summon)` -> Stunned."""
    assert ABILITY_CLASSES.get(CHRONOMETRON) is not None, "1226 doit etre dans ABILITY_CLASSES"
    rid = build_runner("777", extra=["--p-units", "necroOverlord,necroDestroyer",
                                     "--a-units", "eldarRanger,astraBullgryn", "--no-ai"])["rid"]
    mkstate, board = _mk(rpc, rid)
    st = mkstate()
    # Le PORTEUR (`necroChronomancer`) est hors seed BC ; l'arbre est caster-AGNOSTIQUE (aucun
    # `GetVariableForLevel`, seulement 2 `GetNumberConstant`), on le force donc depuis un allie present
    # -- meme carve-out que le port caster-agnostique de HarbingerOfDestruction (case-220 §6.7).
    cid = _by_visual(st, "necroOverlord")
    ally = _by_visual(st, "necroDestroyer")
    my_team = st.get_entity(cid).get_component(OwnerComponent).team
    foes = [eid for eid, e in st.entities.items()
            if e.get_component(OwnerComponent) is not None
            and e.get_component(OwnerComponent).team != my_team
            and e.get_component(UnitComponent).alive]
    rng_range = int(GC.ability("Chronometron")["constants"]["range"])
    cp = st.get_entity(cid).get_component(PositionComponent)
    ring = board.neighbours(board.id_at(cp.col, cp.row))
    # 1 ennemi DANS le disque, 1 ennemi HORS du disque, l'allie DANS le disque (temoin d'equipe)
    t_in = board.by_id[ring[0]]
    _place(st, foes[0], t_in["col"], t_in["row"])
    _place(st, foes[1], cp.col, cp.row + rng_range + 3)
    t_ally = board.by_id[ring[1]]
    _place(st, ally, t_ally["col"], t_ally["row"])

    diag = _cast(st, cid, cid, CHRONOMETRON)
    assert diag.get("ported") is True
    assert diag["range"] == rng_range
    posed = {}
    for e in diag["effects"]:
        posed.setdefault(e["target"], set()).add(e["effect_type"])
    assert set(posed) == {foes[0]}, (posed, foes, ally, cid)
    assert posed[foes[0]] == {1065, 1550}, posed          # Pinned + Chronometron_ExtraDamage

    # branche SUMMON : meme etat, meme cast, le trait est la SEULE variable -> Stunned au lieu de Pinned
    st2 = mkstate()
    _place(st2, foes[0], t_in["col"], t_in["row"])
    _place(st2, foes[1], cp.col, cp.row + rng_range + 3)
    _place(st2, ally, t_ally["col"], t_ally["row"])
    sc = st2.get_entity(foes[0]).get_component(StatsComponent)
    sc.ctx.traits = set(getattr(sc.ctx, "traits", None) or ()) | {"Summon"}
    diag2 = _cast(st2, cid, cid, CHRONOMETRON)
    posed2 = {e["effect_type"] for e in diag2["effects"] if e["target"] == foes[0]}
    assert posed2 == {1162, 1550}, posed2                 # Stunned + Chronometron_ExtraDamage
