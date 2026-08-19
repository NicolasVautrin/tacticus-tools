"""GARDE live des masques de ciblage du module `splash` (#247).

Le probe MESURE (`probe_247_splash_targeting.py`), ce test GARDE : il rejoue l'accord entre le gate
natif (`abilityReason` -> `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`) et le
port (`engine/runner/abilities/targeting.get_invalid_target_reason`) pour les DEUX porteurs LINEUP
du module, sur le meme etat fige :

    1000 GauntletsOfUltramar (ultraCalgar)   masque 0x4000, self_cast, CustomRange(2)
    1105 CrushingClaws       (tyranTyrantGuard) masque 0x4000, RANGE_ADJACENT

Ce que le test EXIGE, et pourquoi chaque exigence est la :
  * accord natif/port sur TOUTES les lignes -- le fond ;
  * au moins une ligne ACCEPTEE (0x0) -- sans elle, « le natif refuse tout » ne distingue pas le
    masque d'une ability indisponible (`AttackQuery$$GetInvalidTargetReason` court-circuite a `0x1`) ;
  * au moins une ligne ou le natif REFUSE alors que `TARGETING_OPTIONS = None` rendait 0 -- c'est la
    regression PERMISSIVE que le masque ferme, et elle doit rester demontree ;
  * les DEUX seuils de portee : 1000 accepte d=2 et refuse d=3 (`CustomRange(2)`), 1105 accepte d=1
    et refuse d>=2 (`RANGE_ADJACENT` -> branche `AreEntitiesAdjacent`). Ce sont les cas limites, et
    ils separent les deux regimes de portee du lot.

Les items 1051/1078/1098 sont gardes AILLEURS, par `test_splash_range_clamp_live.py` (#243) : leurs
porteurs sont des SUMMONS, amenes par catalogue injecte + trait `Summon` retire, et leur montage
exige un ennemi AU CONTACT pour exercer le clamp de melee -- une geometrie que le montage d'ici ne
produit pas. 1065 `ScythingTalons` reste le SEUL item du module sans mesure live (son porteur
`tyranSmnWarrior` est joignable par la meme voie ; residu nomme, cf.
`docs/rl/case-243-splash-range-clamp.md` §6).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import get_invalid_target_reason
from engine.runner.abilities.targeting_rule import TargetingRule as TR

import probe_247_splash_targeting as P

GAUNTLETS = 1000
CRUSHING = 1105


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


@pytest.fixture(scope="module")
def montage():
    """Monte UNE fois le runner + la geometrie, et rend l'etat fige (natif + port) pour les deux
    abilities. Dispose SON runner (jamais ceux des autres)."""
    from rl_collect_batch import _resolve_session, _rpc
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state

    sid = _resolve_session()
    grp = P.GROUPS["heroes"]
    rid, state_file = P._build(sid, "777", "MC1_67", grp["p_units"])
    try:
        for _ in range(P.TOURS_DE_CHAUFFE):
            P._act(sid, rid, {"kind": "endturn"}, 60)
        anchor = grp["p_units"][0]
        P._drive_spectrum(sid, rid, anchor)
        P._bring_to_contact(sid, rid, [v for v in grp["p_units"] if v != anchor])
        P._give_turn_to(sid, rid, anchor)

        dv = P._dv(sid, rid)
        ob = P._r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = P._r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = P._r(sid, "boardGraph", {"runnerId": rid}, 90)
        assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indisponible"
        st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))

        out = {}
        for vis, aid in grp["casters"]:
            cu = P._find_carrier(sid, rid, dv, vis, aid)
            assert cu is not None, "porteur %s absent du plateau (ability %d)" % (vis, aid)
            nat0 = P._nat(sid, rid, int(cu["id"]), aid)
            assert ((nat0 or {}).get("abilityState") or {}).get("usable"), (
                "ability %d non utilisable par %s -> l'oracle court-circuite (`ValidRequest`)"
                % (aid, vis))
            rows = P._measure(sid, rid, st, dv, cu, aid, ["apres", "avant"])
            out[aid] = {"caster": cu, "rows": rows, "state": st}
        yield out
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
        except Exception:                                            # noqa: BLE001
            pass


@pytest.mark.parametrize("aid", [GAUNTLETS, CRUSHING])
def test_accord_natif_port(montage, aid):
    rows = montage[aid]["rows"]
    assert rows, "aucune ligne mesuree pour %d" % aid
    bad = [(r["label"], r["dist"], hex(r["nat"] or 0), hex(r["apres"])) for r in rows
           if r["nat"] != r["apres"]]
    assert not bad, ("desaccord natif/port sur %d : %s" % (aid, bad))
    assert any(r["nat"] == 0 for r in rows), (
        "aucune cible ACCEPTEE pour %d -> impossible de distinguer « le masque refuse » de "
        "« l'ability est indisponible »" % aid)


@pytest.mark.parametrize("aid", [GAUNTLETS, CRUSHING])
def test_le_masque_ferme_des_casts_que_master_acceptait(montage, aid):
    """`TARGETING_OPTIONS = None` (l'etat d'avant cette tranche) rendait 0 sur des lignes que le
    natif REFUSE : c'est la degradation PERMISSIVE que le masque ferme."""
    rows = montage[aid]["rows"]
    gains = [r for r in rows if r["nat"] not in (None, 0) and r["avant"] == 0]
    assert gains, ("aucun cast illegal ferme par le masque de %d -- l'etat monte ne discrimine "
                   "rien" % aid)


def test_gauntlets_seuil_de_portee_custom_range_2(montage):
    """`SelfCastIfEnemyInCustomRangeOptions(2)` -> `overrideRange = 2`, `onlyAdjacent =
    RangedBool.False` : le filtre statique compare `hexDistance <= 2`. d=2 passe, d=3 rompt sur
    `TargetIsInRange`."""
    rows = [r for r in montage[GAUNTLETS]["rows"] if r["label"].startswith("ENNEMI")]
    d2 = [r for r in rows if r["dist"] == 2]
    d3 = [r for r in rows if r["dist"] >= 3]
    assert d2 and d3, "spectre insuffisant (d=2 et d>=3 requis) : %s" % [r["dist"] for r in rows]
    assert all(r["nat"] == 0 and r["apres"] == 0 for r in d2), d2
    assert all(r["nat"] == int(TR.TargetIsInRange) and r["apres"] == int(TR.TargetIsInRange)
               for r in d3), d3


def test_crushing_claws_seuil_adjacence(montage):
    """`RANGE_ADJACENT` (onlyAdjacent = `RangedBool.True`) -> le filtre prend la branche
    `battleQuery.AreEntitiesAdjacent`, PAS un `dist <= N` : d=1 passe, d>=2 rompt."""
    rows = [r for r in montage[CRUSHING]["rows"] if r["label"].startswith("ENNEMI")]
    d1 = [r for r in rows if r["dist"] == 1]
    dfar = [r for r in rows if r["dist"] >= 2]
    assert d1 and dfar, "spectre insuffisant (d=1 et d>=2 requis) : %s" % [r["dist"] for r in rows]
    assert all(r["nat"] == 0 and r["apres"] == 0 for r in d1), d1
    assert all(r["nat"] == int(TR.TargetIsInRange) and r["apres"] == int(TR.TargetIsInRange)
               for r in dfar), dfar


def test_gauntlets_self_cast_aiguille_hors_du_filtre_statique(montage):
    """`isSelfCasting = 1` (le byte `options+0x00` pose par la factory) : quand la cible EST le
    caster, l'overload 5 arguments branche sur `GetCasterNotAddedReason` et n'evalue JAMAIS la
    cascade -- donc `TargetIsEnemy` ne s'applique pas au self-cast. Sans `self_cast`, le port
    refuserait `0x4000` un cast que le natif accepte (contrefactuel `sansSelf` du probe)."""
    rows = montage[GAUNTLETS]["rows"]
    st = montage[GAUNTLETS]["state"]
    cid = int(montage[GAUNTLETS]["caster"]["id"])
    me = [r for r in rows if r["targetId"] == cid]
    assert me, "le caster n'est pas dans les lignes mesurees"
    assert me[0]["nat"] == 0 and me[0]["apres"] == 0, me
    faux = int(get_invalid_target_reason(st, cid, cid, P._variant(GAUNTLETS, "sansSelf")))
    assert faux == int(TR.TargetIsEnemy), (
        "le contrefactuel `sansSelf` devrait faux-REFUSER le self-cast sur TargetIsEnemy, "
        "il rend 0x%x" % faux)


def test_crushing_claws_refuse_le_self_cast(montage):
    """Pendant exact : 1105 ne pose PAS `isSelfCasting`, donc le caster traverse le filtre statique
    et `TargetIsEnemy` le refuse. Deux abilities du meme module, deux verdicts opposes sur la MEME
    ligne « cible = le caster »."""
    rows = montage[CRUSHING]["rows"]
    cid = int(montage[CRUSHING]["caster"]["id"])
    me = [r for r in rows if r["targetId"] == cid]
    assert me, "le caster n'est pas dans les lignes mesurees"
    assert me[0]["nat"] == int(TR.TargetIsEnemy), me
    assert me[0]["apres"] == int(TR.TargetIsEnemy), me


@pytest.mark.parametrize("aid", [GAUNTLETS, CRUSHING])
def test_masque_present_et_decompose_sans_residu(aid):
    """Garde OFFLINE (aucun runner) : le masque est pose, ses bits se nomment tous dans
    `targeting_rule.py`, et `range` accompagne toujours `rules`."""
    opts = getattr(ABILITY_CLASSES[aid], "TARGETING_OPTIONS", None)
    assert opts is not None, "masque absent pour %d" % aid
    assert opts.range is not None, "volet PORTEE non arme pour %d" % aid
    reste = int(opts.rules)
    for bit in TR:
        reste &= ~int(bit)
    assert reste == 0, "bits non nommes dans le masque de %d : 0x%x" % (aid, reste)
