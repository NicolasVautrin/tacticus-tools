"""#433-r4-r1-r1 -- `WallOfMirrors` (1186) CONFRONTEE au natif, les DEUX faces separement.

L'ability n'a que des porteurs hors-jeu (`tauNpc5StealthSuit` npc, `tauSmnStealthSuit` summon SANS
invocateur) : elle est amenee en bataille par GREFFE sur `tauCrisis`
(`docs/rl/case-92-catalog-injection.md` §5bis ; condition etablie au decompile, cf. le probe).

FACE DECISION -- l'ORACLE 1 BIT. `WallOfMirrorsAbility$$GetDynamicInvalidTargetReason` n'a que DEUX
conjoints, et le RPC `abilityReason` rend le masque `TargetingRule` rompu, cible par cible :

    valide  <=>  la cible porte Markerlight (0x462)  ET  `GetPossibleTiles()` est non vide

Le test exerce les DEUX conjoints SEPAREMENT, dans le MEME etat -- c'est ce qui le rend
discriminant (un accord sur deux « non » ne prouverait rien) :

  * cible MARQUEE, anneau libre        -> natif 0x0                       (les deux conjoints vrais)
  * cible NON marquee, anneau libre    -> natif 0x2 TargetMatchesDynamicRule (1er conjoint faux)

⚠ `abilityTargets` NE convient PAS : il n'enumere que les unites du `toActivate` courant (mesure :
`unitCount = 0` pour un caster hors tour), donc son zero serait un zero de HARNAIS.

FACE EXECUTION -- la TUILE D'ATTERRISSAGE. Le cast LIVE est compare au replay OFFLINE du port sur la
MEME capture et le MEME `state.rng` (`dumpRng`) : `First(SortTilesByUtility(GetPossibleTiles(),
Caster, UtilityType(7)))` est DETERMINISTE (zero tirage), donc l'egalite des deux tuiles est une
mesure forte de tout l'arbre de ciblage.

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268).
ASCII only. Probe jumeau : `scripts/python/probe_433_r4_r1_r1_wall_of_mirrors.py`.
"""
from __future__ import annotations

import pytest

import probe_433_r4_r1_r1_wall_of_mirrors as P
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.loki import wall_of_mirrors_possible_tiles, wall_of_mirrors_range
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.components import PositionComponent
from engine.runner.snapshot import load_state

MARKERLIGHT = int(EffectType.Markerlight)


@pytest.fixture(scope="module")
def wom(live_session, rpc):
    """Le montage COMPLET, monte UNE fois : greffe de 1186 sur `tauCrisis`, Markerlight pose par la
    voie NATURELLE (l'attaque normale 1076 de `tauMarksman`), capture + `dumpRng`, replay OFFLINE du
    port, puis cast LIVE. Le runner est dispose au teardown."""
    P.CASTER_TILE, P.MARKER_TILE = "2,6", "3,2"
    P.TGT_MARK_TILE, P.TGT_PLAIN_TILE = "2,4", "2,8"
    rid = P.build(hp_target=400000)
    try:
        P.ensure_my_turn(rid)
        holders = P.mark(rid)
        assert holders, "montage invalide : le tir de %s n'a pose AUCUN Markerlight" % P.MARKER_VID
        u = P._units(rid)
        ids = {v: i for v, (i, _p, _h, _e) in u.items()}
        cid, tid_mark, tid_plain = (ids[P.CASTER_VID], ids[P.TGT_MARK_VID], ids[P.TGT_PLAIN_VID])
        assert MARKERLIGHT in u[P.TGT_MARK_VID][3]
        assert MARKERLIGHT not in u[P.TGT_PLAIN_VID][3], \
            "montage invalide : les deux cibles sont marquees -> aucun contraste"

        reasons = {vid: P.native_reason(rid, cid, ids[vid])
                   for vid in (P.TGT_MARK_VID, P.TGT_PLAIN_VID)}

        board = Board(rpc("boardGraph", {"runnerId": rid}, 60)["tiles"], adjacency="native_sym")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        tm = rpc("tileMeta", {"runnerId": rid}, 90)
        s = rpc("dumpRng", {"runnerId": rid}, 30)
        assert isinstance(s, dict) and s.get("ok"), "dumpRng indisponible -> pas de replay cale"

        st = load_state(dv, ob, snap, board=board, tiles=tm)
        from engine.runner.prng import IntBasedMersenneTwister
        rng = IntBasedMersenneTwister()
        rng.mt, rng.mti = list(s["mt"]), s["mti"]
        st.rng = rng
        ab = ABILITY_CLASSES[1186]()
        port_reasons = {vid: ab.get_dynamic_invalid_target_reason(st, cid, ids[vid])
                        for vid in (P.TGT_MARK_VID, P.TGT_PLAIN_VID)}
        port_tiles = {vid: sorted(board.coord(t) for t in wall_of_mirrors_possible_tiles(
            wall_of_mirrors_range()).select(entities_from_state(st, cid, ids[vid])))
            for vid in (P.TGT_MARK_VID, P.TGT_PLAIN_VID)}
        ab.execute_behaviour(st, cid, tid_mark)
        pc = st.get_entity(cid).get_component(PositionComponent)
        port_landing = (pc.col, pc.row)

        import subprocess
        import sys
        subprocess.run([sys.executable, "rl_duel.py", "act", "ability", "--caster", str(cid),
                        "--ability", "1186", "--target", str(tid_mark),
                        "--state-file", str(P.STATE), "--runner", str(rid)],
                       cwd=str(P.HERE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
        nat_landing = P._units(rid)[P.CASTER_VID][1]
        yield {"rid": rid, "reasons": reasons, "port_reasons": port_reasons,
               "port_tiles": port_tiles, "port_landing": port_landing,
               "nat_landing": nat_landing, "before": u}
    finally:
        P._run(["dispose", "--state-file", str(P.STATE), "--runner", str(rid)])


def test_le_gate_dynamique_refuse_une_cible_non_marquee(wom):
    """1er conjoint ISOLE : la cible NON marquee est refusee par le LITTERAL `2`
    (`TargetingRule.TargetMatchesDynamicRule`) alors que son anneau, lui, n'est PAS vide."""
    assert wom["reasons"][P.TGT_PLAIN_VID] == int(TR.TargetMatchesDynamicRule)
    assert wom["port_tiles"][P.TGT_PLAIN_VID], \
        "regime non discriminant : l'anneau de la cible non marquee doit etre NON vide"


def test_le_gate_dynamique_accepte_une_cible_marquee(wom):
    """2e regime : Markerlight ET anneau non vide -> le natif ne rompt AUCUNE regle."""
    assert wom["reasons"][P.TGT_MARK_VID] == 0
    assert wom["port_tiles"][P.TGT_MARK_VID]


def test_le_port_rend_le_meme_bit_que_le_natif(wom):
    """L'oracle, cible par cible. Le test serait vide si les deux verdicts coincidaient : la
    non-degenerescence est verifiee ICI."""
    assert wom["port_reasons"] == wom["reasons"]
    assert wom["reasons"][P.TGT_MARK_VID] != wom["reasons"][P.TGT_PLAIN_VID], \
        "regime DEGENERE : les deux cibles rendent le meme verdict"


def test_la_tuile_d_atterrissage_du_port_est_celle_du_natif(wom):
    """Face EXECUTION : `FlyUnit(Caster, First(SortTilesByUtility(GetPossibleTiles(), Caster, 7)))`.
    Deterministe -> egalite EXACTE exigee, et le caster doit avoir REELLEMENT bouge."""
    assert wom["port_landing"] == wom["nat_landing"]
    assert wom["nat_landing"] != wom["before"][P.CASTER_VID][1], \
        "le caster n'a pas bouge -> le vol n'a rien exerce"
    assert wom["nat_landing"] in wom["port_tiles"][P.TGT_MARK_VID], \
        "la tuile d'atterrissage doit appartenir a `GetPossibleTiles()`"
